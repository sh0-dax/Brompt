"""Tests for Template Engine."""
from brompt.core.template_engine import (
    Template,
    TemplateRegistry,
    create_builtin_templates,
    template_registry,
)


class TestTemplateFilters:
    def test_upper_filter(self):
        t = Template("Hello {{ name|upper }}!", name="test")
        assert t.render(name="world") == "Hello WORLD!"

    def test_lower_filter(self):
        t = Template("Hello {{ name|lower }}!", name="test")
        assert t.render(name="WORLD") == "Hello world!"

    def test_capitalize_filter(self):
        t = Template("{{ text|capitalize }}", name="test")
        assert t.render(text="hello world") == "Hello world"

    def test_trim_filter(self):
        t = Template("'{{ text|trim }}'", name="test")
        assert t.render(text="  hello  ") == "'hello'"

    def test_title_filter(self):
        t = Template("{{ text|title }}", name="test")
        assert t.render(text="hello world") == "Hello World"

    def test_json_filter(self):
        t = Template("{{ data|json }}", name="test")
        result = t.render(data={"key": "value"})
        assert '"key"' in result
        assert '"value"' in result


class TestTemplateVariables:
    def test_simple_variable(self):
        t = Template("Hello {{ name }}!", name="test")
        assert t.render(name="World") == "Hello World!"

    def test_multiple_variables(self):
        t = Template("{{ a }} and {{ b }}", name="test")
        assert t.render(a="foo", b="bar") == "foo and bar"

    def test_missing_variable(self):
        t = Template("Hello {{ name }}!", name="test")
        assert t.render() == "Hello !"

    def test_empty_template(self):
        t = Template("", name="test")
        assert t.render() == ""


class TestTemplateConditions:
    def test_if_true(self):
        t = Template("{% if show %}visible{% endif %}", name="test")
        assert t.render(show=True) == "visible"

    def test_if_false(self):
        t = Template("{% if show %}visible{% endif %}", name="test")
        assert t.render(show=False) == ""

    def test_if_else(self):
        t = Template("{% if cond %}yes{% else %}no{% endif %}", name="test")
        assert t.render(cond=True) == "yes"
        assert t.render(cond=False) == "no"

    def test_if_eq(self):
        t = Template("{% if x == 1 %}one{% endif %}", name="test")
        assert t.render(x=1) == "one"
        assert t.render(x=2) == ""

    def test_if_in(self):
        t = Template("{% if 'a' in items %}found{% endif %}", name="test")
        assert t.render(items="abc") == "found"
        assert t.render(items="xyz") == ""


class TestTemplateLoops:
    def test_simple_loop(self):
        t = Template("{% for item in items %}{{ item }},{% endfor %}", name="test")
        result = t.render(items=["a", "b"])
        assert result == "a,b,"

    def test_empty_loop(self):
        t = Template("{% for item in items %}{{ item }}{% endfor %}", name="test")
        assert t.render(items=[]) == ""


class TestTemplateErrors:
    def test_invalid_filter(self):
        t = Template("{{ x|nonexistent }}", name="test")
        result = t.render(x="hello")
        assert result == "hello"


class TestTemplateRegistry:
    def test_register_and_get(self):
        reg = TemplateRegistry()
        t = Template("Hello {{ name }}!", name="greeting")
        reg.register("greeting", t)
        assert reg.get("greeting") is t

    def test_get_nonexistent(self):
        reg = TemplateRegistry()
        assert reg.get("nonexistent") is None

    def test_render(self):
        reg = TemplateRegistry()
        t = Template("Hello {{ user }}!", name="greeting")
        reg.register("greeting", t)
        assert reg.render("greeting", user="World") == "Hello World!"

    def test_list(self):
        reg = TemplateRegistry()
        t1 = Template("a", name="t1")
        t2 = Template("b", name="t2")
        reg.register("t1", t1)
        reg.register("t2", t2)
        names = reg.list()
        assert "t1" in names
        assert "t2" in names


class TestBuiltinTemplates:
    def test_create_builtin_has_six_templates(self):
        reg = create_builtin_templates()
        names = reg.list()
        assert "chat" in names
        assert "code_review" in names
        assert "summarize" in names
        assert "translate" in names
        assert "analysis" in names
        assert "debug" in names

    def test_chat_template_renders(self):
        result = template_registry.render("chat", user_message="Hello", system_prompt="You are helpful.")
        assert result is not None
        assert "Hello" in result or "You are" in result

    def test_code_review_template_renders(self):
        result = template_registry.render("code_review", code="print('hi')", language="python")
        assert result is not None
