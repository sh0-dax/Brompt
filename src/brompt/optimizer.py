import re
from typing import Optional


class TokenOptimizer:
    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def compress_context(messages: list, max_messages: int = 4) -> list:
        if not messages:
            return []
        recent = messages[-max_messages:]
        compressed = []
        for msg in recent:
            content = msg.get("content", "")
            if len(content) > 500:
                content = content[:250] + " [...] " + content[-150:]
            compressed.append({"role": msg.get("role", "user"), "content": content})
        return compressed

    @staticmethod
    def summarize_history(messages: list) -> str:
        if len(messages) <= 6:
            return ""
        user_msgs = [m["content"][:60] for m in messages if m.get("role") == "user"]
        if not user_msgs:
            return ""
        topics = " ; ".join(user_msgs[-3:])
        return f"[History summary]: {topics}"

    @staticmethod
    def remove_redundant_whitespace(text: str) -> str:
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    @staticmethod
    def remove_duplicate_content(text: str) -> str:
        lines = text.split("\n")
        seen = set()
        unique = []
        for line in lines:
            normalized = "".join(line.lower().split())
            if normalized not in seen or len(normalized) < 15:
                seen.add(normalized)
                unique.append(line)
        return "\n".join(unique)

    def build_api_messages(
        self,
        system_prompt: str,
        user_input: str,
        template_content: str,
        messages_history: Optional[list] = None,
        is_first_message: bool = True,
        max_context: int = 4,
    ) -> tuple[list[dict], dict]:
        original_tokens = 0
        messages = []

        if is_first_message and system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            original_tokens += self.estimate_tokens(system_prompt)
        elif system_prompt:
            original_tokens += self.estimate_tokens(system_prompt)

        if messages_history:
            history_tokens = sum(
                self.estimate_tokens(m.get("content", ""))
                for m in messages_history
            )
            original_tokens += history_tokens

            if not is_first_message and max_context > 0:
                recent = messages_history[-max_context:]
                for msg in recent:
                    content = msg.get("content", "")
                    if len(content) > 500:
                        content = content[:250] + " [...] " + content[-150:]
                    messages.append({
                        "role": msg.get("role", "user"),
                        "content": content,
                    })

        current_content = template_content + "\n\n" + user_input
        messages.append({"role": "user", "content": current_content})
        original_tokens += self.estimate_tokens(template_content) + self.estimate_tokens(user_input)

        optimized_tokens = sum(self.estimate_tokens(m["content"]) for m in messages)
        saved_tokens = max(0, original_tokens - optimized_tokens)

        stats = {
            "original_tokens": original_tokens,
            "optimized_tokens": optimized_tokens,
            "saved_tokens": saved_tokens,
            "savings_percent": (saved_tokens / original_tokens * 100) if original_tokens > 0 else 0,
        }

        return messages, stats

    def build_optimized_prompt(
        self,
        system_prompt: str,
        user_input: str,
        template_content: str,
        messages_history: Optional[list] = None,
        is_first_message: bool = True,
    ) -> tuple[str, dict]:
        original_tokens = 0
        parts = []

        if is_first_message and system_prompt:
            parts.append(system_prompt)
            original_tokens += self.estimate_tokens(system_prompt)
        elif system_prompt:
            original_tokens += self.estimate_tokens(system_prompt)

        if messages_history:
            history_tokens = sum(
                self.estimate_tokens(m.get("content", ""))
                for m in messages_history
            )
            original_tokens += history_tokens

            if not is_first_message:
                if len(messages_history) > 6:
                    summary = self.summarize_history(messages_history)
                    if summary:
                        parts.append(summary)

                compressed = self.compress_context(messages_history)
                context_text = "\n".join(
                    f"[{m['role']}]: {m['content']}" for m in compressed
                )
                if context_text:
                    parts.append(context_text)

        parts.append(template_content)
        original_tokens += self.estimate_tokens(template_content) + self.estimate_tokens(user_input)

        final_prompt = "\n\n".join(p for p in parts if p)
        final_prompt = self.remove_redundant_whitespace(final_prompt)
        final_prompt = self.remove_duplicate_content(final_prompt)

        optimized_tokens = self.estimate_tokens(final_prompt)
        saved_tokens = max(0, original_tokens - optimized_tokens)

        stats = {
            "original_tokens": original_tokens,
            "optimized_tokens": optimized_tokens,
            "saved_tokens": saved_tokens,
            "savings_percent": (saved_tokens / original_tokens * 100) if original_tokens > 0 else 0,
        }

        return final_prompt, stats
