"""
Auto-detect agent — analyses user input to suggest template, model, and parameters.
Detection with TaskType enum, complexity analysis, language detection, and model recommendations.
"""

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskType(str, Enum):
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    CODE_DEBUG = "debugging"
    CONTENT_WRITING = "content_writing"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    ANALYSIS = "analysis"
    COMPARISON = "comparison"
    BRAINSTORMING = "brainstorming"
    EXPLANATION = "explanation"
    QA = "qa"
    CREATIVE_WRITING = "creative_writing"
    DATA_EXTRACTION = "data_extraction"
    STEP_BY_STEP = "step_by_step"
    EDITING = "editing"
    COACHING = "coaching"
    RESEARCH = "research"
    GENERAL = "default"


class ComplexityLevel(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    EXPERT = "expert"


@dataclass
class ModelRecommendation:
    provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2000
    reason: str = ""


@dataclass
class TaskDetection:
    task_type: TaskType
    complexity: ComplexityLevel
    confidence: float
    detected_language: str
    suggested_template: str
    suggested_model: ModelRecommendation
    extracted_entities: dict = field(default_factory=dict)
    reasoning: str = ""


@dataclass
class DetectionResult:
    """Legacy result type — kept for backward compatibility."""
    task_type: str
    suggested_template: str
    confidence: float
    suggested_model: dict = field(default_factory=lambda: {
        "model": "",
        "temperature": 0.7,
        "max_tokens": 2000,
    })
    reasoning: str = ""


_TASK_PATTERNS_CONFIG = [
    (TaskType.CODE_GENERATION, "code", r"(write|create|implement|generate|build|make)\s.*(function|class|script|program|app|api|endpoint|server)", 0.85, {"model": "", "temperature": 0.2, "max_tokens": 3000}),
    (TaskType.CODE_GENERATION, "sql", r"(sql|query|select|insert|update|delete|join|database|table)", 0.8, {"model": "", "temperature": 0.1, "max_tokens": 1500}),
    (TaskType.CODE_REVIEW, "code_review", r"(review|audit|inspect|check)\s.*(code|pull request|pr|diff|commit)", 0.8, {"model": "", "temperature": 0.3, "max_tokens": 2000}),
    (TaskType.CODE_DEBUG, "debugging", r"(bug|error|crash|exception|fail|broken|not working|issue|traceback|stack trace)", 0.85, {"model": "", "temperature": 0.3, "max_tokens": 2000}),
    (TaskType.TRANSLATION, "translate", r"(translate|ترجمه|перевод|Übersetzung|traduction|traducción|translation)", 0.9, {"model": "", "temperature": 0.3, "max_tokens": 1500}),
    (TaskType.SUMMARIZATION, "summarize", r"(summarize|summarise|summary|tl;dr|tl dr|brief|gist|key points)", 0.85, {"model": "", "temperature": 0.4, "max_tokens": 1000}),
    (TaskType.EXPLANATION, "explain", r"(explain|what is|how does|describe|define|tell me about|clarify)", 0.8, {"model": "", "temperature": 0.5, "max_tokens": 1500}),
    (TaskType.QA, "qa", r"(\?$|what|why|who|when|where|which|how\s)", 0.7, {"model": "", "temperature": 0.3, "max_tokens": 1000}),
    (TaskType.ANALYSIS, "analysis", r"(analyze|analyse|compare|contrast|evaluate|assess|pros.cons|impact)", 0.8, {"model": "", "temperature": 0.4, "max_tokens": 2000}),
    (TaskType.BRAINSTORMING, "brainstorm", r"(brainstorm|ideas|suggestions|creative|innovative|think of)", 0.75, {"model": "", "temperature": 0.9, "max_tokens": 1500}),
    (TaskType.CONTENT_WRITING, "article", r"(write.*(article|essay|post|blog|story|content|draft))", 0.8, {"model": "", "temperature": 0.7, "max_tokens": 2500}),
    (TaskType.CONTENT_WRITING, "email", r"(email|mail|newsletter|reply|compose.*message)", 0.8, {"model": "", "temperature": 0.5, "max_tokens": 1000}),
    (TaskType.CREATIVE_WRITING, "creative", r"(story|poem|narrative|fiction|creative|imaginative)", 0.8, {"model": "", "temperature": 0.9, "max_tokens": 2000}),
    (TaskType.EDITING, "rewrite", r"(rewrite|rephrase|paraphrase|improve|polish|edit|refine)", 0.8, {"model": "", "temperature": 0.4, "max_tokens": 1500}),
    (TaskType.COACHING, "coach", r"(advice|help me|guidance|how can I|tips|recommend|suggest|coach)", 0.7, {"model": "", "temperature": 0.6, "max_tokens": 1000}),
    (TaskType.RESEARCH, "research", r"(research|investigate|study|find.*information|look up|what.*known)", 0.75, {"model": "", "temperature": 0.3, "max_tokens": 2000}),
    (TaskType.STEP_BY_STEP, "learning", r"(step by step|step-by-step|guide|tutorial|walkthrough|how to)", 0.8, {"model": "", "temperature": 0.4, "max_tokens": 2000}),
    (TaskType.COMPARISON, "compare", r"(compare|comparison|versus|vs\.?|difference between)", 0.85, {"model": "", "temperature": 0.3, "max_tokens": 1500}),
    (TaskType.DATA_EXTRACTION, "extract", r"(extract|parse|scrape|get.*data|pull.*information)", 0.8, {"model": "", "temperature": 0.2, "max_tokens": 1500}),
]

_MODEL_RECOMMENDATIONS = {
    (TaskType.CODE_GENERATION, ComplexityLevel.SIMPLE): ModelRecommendation(
        provider="openai", model="gpt-3.5-turbo", temperature=0.3, max_tokens=1000,
        reason="Simple code task - lightweight model sufficient",
    ),
    (TaskType.CODE_GENERATION, ComplexityLevel.COMPLEX): ModelRecommendation(
        provider="openai", model="gpt-4", temperature=0.3, max_tokens=2000,
        reason="Complex code - needs advanced model",
    ),
    (TaskType.CODE_GENERATION, ComplexityLevel.EXPERT): ModelRecommendation(
        provider="anthropic", model="claude-3-opus", temperature=0.2, max_tokens=4000,
        reason="Expert-level code - best model needed",
    ),
    (TaskType.CONTENT_WRITING, ComplexityLevel.COMPLEX): ModelRecommendation(
        provider="anthropic", model="claude-3-sonnet", temperature=0.7, max_tokens=3000,
        reason="Complex writing - Claude better for style",
    ),
    (TaskType.TRANSLATION, ComplexityLevel.SIMPLE): ModelRecommendation(
        provider="openai", model="gpt-3.5-turbo", temperature=0.1, max_tokens=500,
        reason="Simple translation - lightweight model",
    ),
    (TaskType.SUMMARIZATION, ComplexityLevel.SIMPLE): ModelRecommendation(
        provider="openai", model="gpt-3.5-turbo", temperature=0.3, max_tokens=300,
        reason="Simple summary - lightweight model",
    ),
    (TaskType.QA, ComplexityLevel.SIMPLE): ModelRecommendation(
        provider="openai", model="gpt-3.5-turbo", temperature=0.5, max_tokens=500,
        reason="Simple Q&A - lightweight model",
    ),
    (TaskType.EXPLANATION, ComplexityLevel.SIMPLE): ModelRecommendation(
        provider="openai", model="gpt-3.5-turbo", temperature=0.5, max_tokens=500,
        reason="Simple explanation - lightweight model",
    ),
}

_DEFAULT_MODEL = ModelRecommendation(
    provider="openai", model="gpt-4", temperature=0.7, max_tokens=2000,
    reason="Default model for general tasks",
)

SHORT_INPUT_THRESHOLD = 15


def _keyword_fallback(text: str) -> TaskDetection:
    text_lower = text.lower()
    words = text_lower.split()

    if any(w in words for w in ["translate", "ترجمة", "translation"]):
        return TaskDetection(task_type=TaskType.TRANSLATION, complexity=ComplexityLevel.SIMPLE, confidence=0.6,
                             detected_language="en", suggested_template="translate", suggested_model=_DEFAULT_MODEL)
    if any(w in words for w in ["code", "function", "class", "script"]):
        return TaskDetection(task_type=TaskType.CODE_GENERATION, complexity=ComplexityLevel.SIMPLE, confidence=0.6,
                             detected_language="en", suggested_template="code", suggested_model=_DEFAULT_MODEL)
    if "?" in text or text_lower.startswith(("what", "why", "how", "who", "when", "where")):
        return TaskDetection(task_type=TaskType.QA, complexity=ComplexityLevel.SIMPLE, confidence=0.6,
                             detected_language="en", suggested_template="qa", suggested_model=_DEFAULT_MODEL)
    if any(w in words for w in ["summarize", "summary", "brief"]):
        return TaskDetection(task_type=TaskType.SUMMARIZATION, complexity=ComplexityLevel.SIMPLE, confidence=0.6,
                             detected_language="en", suggested_template="summarize", suggested_model=_DEFAULT_MODEL)
    if any(w in words for w in ["explain", "what is"]):
        return TaskDetection(task_type=TaskType.EXPLANATION, complexity=ComplexityLevel.SIMPLE, confidence=0.6,
                             detected_language="en", suggested_template="explain", suggested_model=_DEFAULT_MODEL)
    if any(w in words for w in ["compare", "versus", "vs"]):
        return TaskDetection(task_type=TaskType.COMPARISON, complexity=ComplexityLevel.SIMPLE, confidence=0.6,
                             detected_language="en", suggested_template="compare", suggested_model=_DEFAULT_MODEL)

    return TaskDetection(
        task_type=TaskType.GENERAL, complexity=ComplexityLevel.SIMPLE, confidence=0.3,
        detected_language="en", suggested_template="default", suggested_model=_DEFAULT_MODEL,
        reasoning="No clear task pattern detected",
    )


class AutoDetectAgent:
    """Analyse user input and suggest optimal template, model, and generation parameters."""

    def __init__(self, max_cache_entries: int = 1000):
        self._cache: OrderedDict[str, TaskDetection] = OrderedDict()
        self._max_cache_entries = max_cache_entries

    def _cache_get(self, key: str) -> Optional[TaskDetection]:
        if key in self._cache:
            value = self._cache.pop(key)
            self._cache[key] = value
            return value
        return None

    def _cache_put(self, key: str, value: TaskDetection) -> None:
        self._cache[key] = value
        if len(self._cache) > self._max_cache_entries:
            self._cache.popitem(last=False)

    def detect(self, user_input: str) -> TaskDetection:
        cache_key = user_input[:100].lower().strip()
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if not user_input or not user_input.strip():
            result = TaskDetection(
                task_type=TaskType.GENERAL, complexity=ComplexityLevel.SIMPLE,
                confidence=0.0, detected_language=self._detect_language(user_input),
                suggested_template="default", suggested_model=_DEFAULT_MODEL,
                reasoning="Empty input",
            )
            self._cache_put(cache_key, result)
            return result

        if len(user_input.strip()) < SHORT_INPUT_THRESHOLD:
            result = _keyword_fallback(user_input)
            self._cache_put(cache_key, result)
            return result

        best_match: Optional[TaskDetection] = None
        best_score = 0.0

        for task_type, template, pattern, confidence, model_config in _TASK_PATTERNS_CONFIG:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                length_factor = min(1.0, len(user_input) / 100)
                score = confidence * (0.7 + 0.3 * length_factor)
                if score > best_score:
                    complexity = self._detect_complexity(user_input)
                    model_rec = self._recommend_model(task_type, complexity)
                    best_match = TaskDetection(
                        task_type=task_type,
                        complexity=complexity,
                        confidence=round(score, 4),
                        detected_language=self._detect_language(user_input),
                        suggested_template=template,
                        suggested_model=model_rec,
                        extracted_entities=self._extract_entities(user_input),
                        reasoning=f"Matched pattern '{match.group(0)[:60]}'",
                    )
                    best_score = score

        if best_match is None:
            result = _keyword_fallback(user_input)
            result.extracted_entities = self._extract_entities(user_input)
            self._cache_put(cache_key, result)
            return result

        self._cache_put(cache_key, best_match)
        return best_match

    def detect_batch(self, inputs: list[str]) -> list[TaskDetection]:
        return [self.detect(inp) for inp in inputs]

    def _detect_complexity(self, text: str) -> ComplexityLevel:
        if len(text) < 40:
            return ComplexityLevel.SIMPLE
        elif len(text) < 150:
            return ComplexityLevel.MODERATE
        elif len(text) < 400:
            return ComplexityLevel.COMPLEX
        else:
            return ComplexityLevel.EXPERT

    def _detect_language(self, text: str) -> str:
        arabic = len(re.findall(r'[\u0600-\u06FF]', text))
        english = len(re.findall(r'[a-zA-Z]', text))
        if arabic > english * 2:
            return "ar"
        elif english > arabic * 2:
            return "en"
        elif arabic > 0 and english > 0:
            return "mixed"
        return "en"

    def _recommend_model(self, task: TaskType, complexity: ComplexityLevel) -> ModelRecommendation:
        key = (task, complexity)
        if key in _MODEL_RECOMMENDATIONS:
            return _MODEL_RECOMMENDATIONS[key]
        if complexity == ComplexityLevel.SIMPLE:
            return ModelRecommendation(
                provider="openai", model="gpt-3.5-turbo", temperature=0.5, max_tokens=500,
                reason="Simple task - lightweight model saves cost",
            )
        elif complexity == ComplexityLevel.EXPERT:
            return ModelRecommendation(
                provider="openai", model="gpt-4", temperature=0.2, max_tokens=4000,
                reason="Expert task - best model needed",
            )
        return _DEFAULT_MODEL

    def _extract_entities(self, text: str) -> dict:
        entities = {}
        languages = [
            'python', 'javascript', 'java', 'c++', 'rust', 'go', 'typescript',
            'html', 'css', 'sql', 'react', 'django', 'flask', 'node', 'swift', 'kotlin',
        ]
        for lang in languages:
            if lang in text.lower():
                entities['programming_language'] = lang
                break
        word_match = re.search(r'(\d+)\s*(?:words?|كلمة)', text, re.IGNORECASE)
        if word_match:
            entities['target_word_count'] = int(word_match.group(1))
        if re.search(r'\bjson\b', text.lower()):
            entities['output_format'] = 'json'
        elif re.search(r'\btable\b|\bجدول\b', text.lower()):
            entities['output_format'] = 'table'
        elif re.search(r'\bmarkdown\b|\bmd\b', text.lower()):
            entities['output_format'] = 'markdown'
        return entities


auto_detect_agent = AutoDetectAgent()
