"""Template engine — variable interpolation, conditionals, filters, and a built-in template registry."""

import re
import json
from typing import Any, Callable
from datetime import datetime


_FILTERS: dict[str, Callable] = {}


def register_filter(name: str):
    def wrapper(fn: Callable):
        _FILTERS[name] = fn
        return fn
    return wrapper


@register_filter("upper")
def _upper(value: str) -> str:
    return value.upper()


@register_filter("lower")
def _lower(value: str) -> str:
    return value.lower()


@register_filter("capitalize")
def _capitalize(value: str) -> str:
    return value.capitalize()


@register_filter("title")
def _title(value: str) -> str:
    return value.title()


@register_filter("trim")
def _trim(value: str) -> str:
    return value.strip()


@register_filter("json")
def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


@register_filter("now")
def _now(_value: str, fmt: str = "%Y-%m-%d") -> str:
    return datetime.now().strftime(fmt)


_VAR_RE = re.compile(r"\{\{(\s*[\w.]+\s*(?:\|[^}]+)?)\s*\}\}")
_BLOCK_RE = re.compile(r"\{%\s*(if|for|else|endif|endfor)\s*(.*?)\s*%\}")


class TemplateError(Exception):
    pass


class Template:
    """A simple prompt template with variables, filters, and basic control flow."""

    def __init__(self, source: str, name: str = "anonymous"):
        self.source = source
        self.name = name
        self._parsed = self._tokenize(source)

    def _tokenize(self, source: str) -> list[tuple[str, str]]:
        tokens: list[tuple[str, str]] = []
        pos = 0
        for m in _BLOCK_RE.finditer(source):
            if m.start() > pos:
                tokens.append(("text", source[pos:m.start()]))
            tag, arg = m.group(1), m.group(2).strip()
            tokens.append(("block", f"{tag}|{arg}" if arg else tag))
            pos = m.end()
        if pos < len(source):
            tokens.append(("text", source[pos:]))
        return tokens

    def render(self, **kwargs: Any) -> str:
        """Render the template with the given variables."""
        parts: list[str] = []
        condition_stack: list[bool] = []
        loop_stack: list[list[str]] = []
        for_depth: int = 0

        def _eval_var(expr: str) -> str:
            parts_expr = expr.split("|")
            var_path = parts_expr[0].strip()
            filter_names = [f.strip() for f in parts_expr[1:]] if len(parts_expr) > 1 else []
            value: Any = kwargs
            for key in var_path.split("."):
                if isinstance(value, dict):
                    value = value.get(key, "")
                elif hasattr(value, key):
                    value = getattr(value, key)
                else:
                    value = ""
                    break
            for fn_name in filter_names:
                fn_args = fn_name.split()
                fn = _FILTERS.get(fn_args[0])
                if fn:
                    try:
                        value = fn(value, *fn_args[1:]) if len(fn_args) > 1 else fn(value)
                    except Exception:
                        value = str(value)
                else:
                    value = str(value)
            return str(value) if value is not None else ""

        for tok_type, tok_val in self._parsed:
            if tok_type == "text":
                if not condition_stack and not loop_stack and not for_depth:
                    parts.append(tok_val)
                elif loop_stack:
                    loop_stack[-1].append(tok_val)
                elif condition_stack and condition_stack[-1] and not for_depth:
                    parts.append(tok_val)
            elif tok_type == "block":
                if for_depth:
                    if tok_val == "endfor":
                        for_depth -= 1
                    continue
                if tok_val.startswith("if|"):
                    cond_expr = tok_val[3:]
                    result = self._eval_condition(cond_expr, kwargs)
                    condition_stack.append(result)
                elif tok_val == "else":
                    if condition_stack:
                        condition_stack[-1] = not condition_stack[-1]
                elif tok_val == "endif":
                    if condition_stack:
                        condition_stack.pop()
                elif tok_val.startswith("for|"):
                    for_depth += 1
                    loop_info = tok_val[4:]
                    parts.append(self._render_for(loop_info, kwargs))
                elif tok_val == "endfor":
                    pass

        result = "".join(parts)
        result = _VAR_RE.sub(lambda m: _eval_var(m.group(1)), result)
        return result

    def _eval_condition(self, expr: str, vars: dict) -> bool:
        tokens = expr.split()
        if len(tokens) == 1:
            return bool(vars.get(tokens[0]))
        if len(tokens) == 3:
            left_val = tokens[0]
            if left_val.startswith("'") or left_val.startswith('"'):
                left = left_val.strip("\"'")
            elif left_val in vars:
                left = str(vars[left_val])
            else:
                left = left_val
            right_val = tokens[2]
            if right_val.startswith("'") or right_val.startswith('"'):
                right = right_val.strip("\"'")
            elif right_val in vars:
                right = str(vars[right_val])
            else:
                right = right_val
            op = tokens[1]
            if op == "==":
                return left == right
            elif op == "!=":
                return left != right
            elif op == "in":
                return left in right
        return False

    def _render_for(self, expr: str, vars: dict) -> str:
        parts = expr.split()
        if len(parts) < 3 or parts[1] != "in":
            return ""
        var_name = parts[0]
        iterable = vars.get(parts[2], [])
        if not isinstance(iterable, (list, tuple)):
            return ""
        inner_tokens = []
        in_for = False
        for tok_type, tok_val in self._parsed:
            if tok_type == "block" and tok_val.startswith("for|"):
                if tok_val[4:] == expr:
                    in_for = True
                continue
            if tok_type == "block" and tok_val == "endfor":
                if in_for:
                    break
                continue
            if in_for:
                inner_tokens.append((tok_type, tok_val))
        results = []
        for item in iterable:
            local_vars = {**vars, var_name: item}
            parts_list = []
            for it_type, it_val in inner_tokens:
                if it_type == "text":
                    rendered = _VAR_RE.sub(lambda m: str(local_vars.get(m.group(1).strip(), "")), it_val)
                    parts_list.append(rendered)
                elif it_type == "block":
                    pass
            results.append("".join(parts_list))
        return "".join(results)


class TemplateRegistry:
    """Registry for named templates."""

    def __init__(self):
        self._templates: dict[str, Template] = {}

    def register(self, name: str, template: Template):
        self._templates[name] = template

    def get(self, name: str) -> Template | None:
        return self._templates.get(name)

    def list(self) -> list[str]:
        return list(self._templates.keys())

    def render(self, name: str, **kwargs) -> str:
        tpl = self.get(name)
        if tpl is None:
            raise TemplateError(f"Template '{name}' not found")
        return tpl.render(**kwargs)


template_registry = TemplateRegistry()


def create_builtin_templates() -> TemplateRegistry:
    reg = TemplateRegistry()

    reg.register("chat", Template(
        "{% if system_prompt %}{{ system_prompt }}\n\n{% endif %}"
        "{% for msg in messages %}"
        "{{ msg.role }}: {{ msg.content }}\n"
        "{% endfor %}"
        "{% if context %}\nAdditional context:\n{{ context }}\n{% endif %}"
        "{{ user_message }}",
        name="chat"
    ))

    reg.register("code_review", Template(
        "Review the following {{ language }} code:\n\n"
        "```{{ language }}\n{{ code }}\n```\n\n"
        "{% if focus_area %}Focus on: {{ focus_area }}\n{% endif %}"
        "Provide feedback on:\n"
        "- Correctness\n- Performance\n- Style\n- Security\n- Edge cases",
        name="code_review"
    ))

    reg.register("summarize", Template(
        "Summarize the following {{ format }}:\n\n{{ content }}\n\n"
        "{% if max_length %}Maximum length: {{ max_length }} words\n{% endif %}"
        "{% if style %}Style: {{ style }}\n{% endif %}"
        "Summary:",
        name="summarize"
    ))

    reg.register("translate", Template(
        "Translate the following {{ source_language }} text to {{ target_language }}:\n\n"
        "{{ text }}\n\n"
        "{% if tone %}Tone: {{ tone }}\n{% endif %}"
        "{% if preserve_formatting %}Preserve formatting: yes\n{% endif %}"
        "Translation:",
        name="translate"
    ))

    reg.register("analysis", Template(
        "Analyze the following {{ data_type }}:\n\n{{ data }}\n\n"
        "{% if aspects %}Aspects to analyze: {{ aspects }}\n{% endif %}"
        "Provide a comprehensive analysis including:\n"
        "- Key findings\n- Patterns and trends\n- Recommendations",
        name="analysis"
    ))

    reg.register("debug", Template(
        "Debug the following {{ language }} code:\n\n"
        "```{{ language }}\n{{ code }}\n```\n\n"
        "{% if error %}Error message: {{ error }}\n{% endif %}"
        "{% if expected_behavior %}Expected behavior: {{ expected_behavior }}\n{% endif %}"
        "Please identify the issue and provide a fix.",
        name="debug"
    ))

    return reg


_builtins = create_builtin_templates()
for name in _builtins.list():
    template_registry.register(name, _builtins.get(name))
