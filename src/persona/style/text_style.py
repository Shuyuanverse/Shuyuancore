# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""文本风格分析器 — 纯规则，零 LLM。

从原始文本提取结构化的语言特征：口头禅、句式、标点习惯、词汇指标、句法特征。
"""
from __future__ import annotations

import re
import math
from collections import Counter
from typing import Dict, List, Any

from .base import BaseStyleExtractor, StyleExtractionResult, StyleConfig


class TextStyleAnalyzer(BaseStyleExtractor):
    """文本风格分析器 — 纯规则，零 LLM。
    
    从原始文本提取：口头禅、句式、标点习惯、词汇指标、句法特征
    """
    
    # 口头禅模式库
    CATCHPHRASE_PATTERNS = {
        "互动型": ["加油", "冲", "奥利给", "牛", "厉害", "绝绝子", "yyds"],
        "强调型": ["真的", "确实", "绝对", "必须", "一定", "千万", "务必"],
        "过渡型": ["然后", "接着", "另外", "还有", "不过", "但是", "而且"],
        "情感型": ["哇", "天哪", "天呐", "我的天", "我的妈", "救命"],
        "开场型": ["首先", "第一", "说起", "关于", "谈到", "提到"],
        "结尾型": ["总之", "所以", "综上", "好了", "就这样", "差不多"],
    }
    
    # 句子开头标记
    SENTENCE_OPENING_MARKERS = ["首先", "然后", "接着", "另外", "不过", "但是", "所以", "因此"]
    
    # 中文标点集合
    PUNCTUATION_SET = set("，。！？、；：""''（）【】《》—……·～")
    
    # 停用词表（用于动态口头禅发现）
    STOPWORDS = set([
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
        "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
        "你", "他", "她", "这", "那", "着", "看", "来", "们", "能",
        "没", "为", "什么", "怎么", "啊", "呢", "吧", "哦", "吗",
    ])
    
    def __init__(self, config: StyleConfig | None = None) -> None:
        """初始化分析器。
        
        Args:
            config: 风格配置，None 则使用默认配置
        """
        self.config = config or StyleConfig()
    
    def extract(self, text: str) -> StyleExtractionResult:
        """从文本中提取风格特征的主入口。
        
        Args:
            text: 输入文本
            
        Returns:
            StyleExtractionResult: 包含所有提取特征的完整结果
        """
        sentences = self._split_sentences(text)
        words = self._tokenize(text)
        
        catchphrases = self._extract_catchphrases(text, sentences)
        dynamic_catchphrases = self._extract_dynamic_catchphrases(text)
        all_catchphrases = {**catchphrases, **dynamic_catchphrases}
        
        sentence_types = self._analyze_sentence_types(sentences)
        sentence_lengths = self._analyze_sentence_lengths(sentences)
        sentence_openings = self._analyze_sentence_openings(sentences)
        sentence_endings = self._analyze_sentence_endings(sentences)
        
        punct_freq = self._analyze_punctuation(text)
        punct_complexity = self._calculate_punctuation_complexity(punct_freq)
        
        ttr = self._calculate_ttr(words)
        word_freq = Counter(words)
        hapax_ratio = self._calculate_hapax_ratio(word_freq)
        avg_word_length = self._calculate_avg_word_length(words)
        
        syntactic_complexity = self._calculate_syntactic_complexity(sentences)
        subordinate_ratio = self._calculate_subordinate_ratio(sentences)
        
        return StyleExtractionResult(
            catchphrases=all_catchphrases,
            sentence_patterns={
                **sentence_types,
                **sentence_lengths,
                **sentence_openings,
                **sentence_endings,
            },
            punctuation_habits=punct_freq,
            vocabulary_metrics={
                "ttr": ttr,
                "hapax_ratio": hapax_ratio,
                "avg_word_length": avg_word_length,
                "punctuation_complexity": punct_complexity,
            },
            syntactic_features={
                "syntactic_complexity": syntactic_complexity,
                "subordinate_ratio": subordinate_ratio,
            },
            raw_features={
                "sentences": sentences,
                "words": words,
                "word_freq": dict(word_freq),
            },
            num_sentences=len(sentences),
            num_words=len(words),
            total_chars=len(text),
        )
    
    def _split_sentences(self, text: str) -> List[str]:
        """中文句子分割（按。！？分割，保留标点）。
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 句子列表
        """
        pattern = r'([^.!?]*[.!?])'
        matches = re.findall(pattern, text)
        sentences = [s.strip() for s in matches if s.strip()]
        
        if not sentences and text.strip():
            sentences = [text.strip()]
        
        return sentences
    
    def _analyze_sentence_types(self, sentences: List[str]) -> Dict[str, float]:
        """句子类型分布（陈述/疑问/感叹比例）。
        
        Args:
            sentences: 句子列表
            
        Returns:
            Dict[str, float]: 各类型比例
        """
        if not sentences:
            return {"declarative": 0.0, "interrogative": 0.0, "exclamatory": 0.0}
        
        declarative = 0
        interrogative = 0
        exclamatory = 0
        
        for sent in sentences:
            if sent.endswith('？') or sent.endswith('?'):
                interrogative += 1
            elif sent.endswith('！') or sent.endswith('!'):
                exclamatory += 1
            else:
                declarative += 1
        
        total = len(sentences)
        return {
            "declarative": declarative / total,
            "interrogative": interrogative / total,
            "exclamatory": exclamatory / total,
        }
    
    def _analyze_sentence_lengths(self, sentences: List[str]) -> Dict[str, float]:
        """句子长度分布（短<10 字/中 10-20/长 20-50/超长>50 的比例）。
        
        Args:
            sentences: 句子列表
            
        Returns:
            Dict[str, float]: 各长度区间比例
        """
        if not sentences:
            return {"short": 0.0, "medium": 0.0, "long": 0.0, "very_long": 0.0}
        
        short = 0
        medium = 0
        long_ = 0
        very_long = 0
        
        for sent in sentences:
            length = len(sent)
            if length < 10:
                short += 1
            elif length < 20:
                medium += 1
            elif length < 50:
                long_ += 1
            else:
                very_long += 1
        
        total = len(sentences)
        return {
            "short": short / total,
            "medium": medium / total,
            "long": long_ / total,
            "very_long": very_long / total,
        }
    
    def _extract_catchphrases(self, text: str, sentences: List[str]) -> Dict[str, float]:
        """基于频率 + 位置的口头禅提取（从 CATCHPHRASE_PATTERNS 匹配）。
        
        Args:
            text: 完整文本
            sentences: 句子列表
            
        Returns:
            Dict[str, float]: 口头禅→频率
        """
        catchphrase_freq: Dict[str, float] = {}
        total_sentences = len(sentences) if sentences else 1
        
        for category, phrases in self.CATCHPHRASE_PATTERNS.items():
            for phrase in phrases:
                count = text.count(phrase)
                if count >= self.config.min_catchphrase_count:
                    freq = count / total_sentences
                    if freq >= self.config.catchphrase_threshold:
                        if self.config.min_catchphrase_length <= len(phrase) <= self.config.max_catchphrase_length:
                            catchphrase_freq[phrase] = freq
        
        return catchphrase_freq
    
    def _extract_dynamic_catchphrases(self, text: str) -> Dict[str, float]:
        """基于 N-gram(2~4) 的动态口头禅发现，过滤停用词后按频率排序。
        
        Args:
            text: 输入文本
            
        Returns:
            Dict[str, float]: 动态发现的口头禅→频率
        """
        words = self._tokenize(text)
        filtered_words = [w for w in words if w not in self.STOPWORDS and len(w) > 1]
        
        if len(filtered_words) < 2:
            return {}
        
        ngram_freq: Dict[str, int] = Counter()
        
        for n in range(2, 5):
            for i in range(len(filtered_words) - n + 1):
                ngram = "".join(filtered_words[i:i+n])
                if self.config.min_catchphrase_length <= len(ngram) <= self.config.max_catchphrase_length:
                    ngram_freq[ngram] += 1
        
        total_ngrams = sum(ngram_freq.values())
        if total_ngrams == 0:
            return {}
        
        dynamic_catchphrases = {}
        for ngram, count in ngram_freq.items():
            freq = count / total_ngrams
            if freq >= self.config.catchphrase_threshold and count >= self.config.min_catchphrase_count:
                if ngram not in self.STOPWORDS:
                    existing = False
                    for existing_phrase in list(dynamic_catchphrases.keys()):
                        if ngram in existing_phrase or existing_phrase in ngram:
                            if dynamic_catchphrases[existing_phrase] < freq:
                                del dynamic_catchphrases[existing_phrase]
                            existing = True
                            break
                    if not existing:
                        dynamic_catchphrases[ngram] = freq
        
        return dynamic_catchphrases
    
    def _analyze_punctuation(self, text: str) -> Dict[str, float]:
        """标点使用频率（各标点出现次数/总标点数）。
        
        Args:
            text: 输入文本
            
        Returns:
            Dict[str, float]: 各标点频率
        """
        punct_counts: Dict[str, int] = Counter()
        
        for char in text:
            if char in self.PUNCTUATION_SET:
                punct_counts[char] += 1
        
        total_punct = sum(punct_counts.values())
        if total_punct == 0:
            return {}
        
        return {punct: count / total_punct for punct, count in punct_counts.items()}
    
    def _calculate_punctuation_complexity(self, punct_freq: Dict[str, float]) -> float:
        """标点复杂度（不同标点种类数/总标点数）。
        
        Args:
            punct_freq: 标点频率字典
            
        Returns:
            float: 复杂度得分 (0-1)
        """
        if not punct_freq:
            return 0.0
        
        num_types = len(punct_freq)
        max_types = len(self.PUNCTUATION_SET)
        
        return min(num_types / max_types, 1.0)
    
    def _tokenize(self, text: str) -> List[str]:
        """分词（jieba 优先，import jieba 失败则字符切分）。
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 分词结果
        """
        if self.config.jieba_available:
            try:
                import jieba
                return list(jieba.cut(text))
            except ImportError:
                pass
        
        return list(text)
    
    def _calculate_ttr(self, words: List[str]) -> float:
        """类符 - 形符比（unique 词数/总词数）。
        
        Args:
            words: 分词结果
            
        Returns:
            float: TTR 值 (0-1)
        """
        if not words:
            return 0.0
        
        unique_words = set(words)
        return len(unique_words) / len(words)
    
    def _calculate_hapax_ratio(self, word_freq: Counter) -> float:
        """只出现 1 次的词数/总词数。
        
        Args:
            word_freq: 词频统计
            
        Returns:
            float: Hapax 比率 (0-1)
        """
        if not word_freq:
            return 0.0
        
        hapax_count = sum(1 for count in word_freq.values() if count == 1)
        total_words = sum(word_freq.values())
        
        return hapax_count / total_words if total_words > 0 else 0.0
    
    def _calculate_avg_word_length(self, words: List[str]) -> float:
        """平均词长。
        
        Args:
            words: 分词结果
            
        Returns:
            float: 平均词长
        """
        if not words:
            return 0.0
        
        total_length = sum(len(word) for word in words)
        return total_length / len(words)
    
    def _analyze_sentence_openings(self, sentences: List[str]) -> Dict[str, float]:
        """句子开头模式频率。
        
        Args:
            sentences: 句子列表
            
        Returns:
            Dict[str, float]: 各开头模式频率
        """
        if not sentences:
            return {}
        
        opening_counts: Dict[str, int] = Counter()
        
        for sent in sentences:
            for marker in self.SENTENCE_OPENING_MARKERS:
                if sent.startswith(marker):
                    opening_counts[marker] += 1
                    break
        
        total = len(sentences)
        return {marker: count / total for marker, count in opening_counts.items() if count > 0}
    
    def _analyze_sentence_endings(self, sentences: List[str]) -> Dict[str, float]:
        """句子结尾模式频率。
        
        Args:
            sentences: 句子列表
            
        Returns:
            Dict[str, float]: 各结尾模式频率
        """
        if not sentences:
            return {}
        
        ending_words = ["总之", "所以", "综上", "好了", "就这样", "差不多", "最后", "因此"]
        ending_counts: Dict[str, int] = Counter()
        
        for sent in sentences:
            for ending in ending_words:
                if sent.endswith(ending):
                    ending_counts[ending] += 1
                    break
        
        total = len(sentences)
        return {ending: count / total for ending, count in ending_counts.items() if count > 0}
    
    def _calculate_syntactic_complexity(self, sentences: List[str]) -> float:
        """句法复杂度（0-1，基于从句比例 + 句子长度方差）。
        
        Args:
            sentences: 句子列表
            
        Returns:
            float: 复杂度得分 (0-1)
        """
        if not sentences:
            return 0.0
        
        clause_ratios = []
        lengths = []
        
        for sent in sentences:
            clause_count = self._count_clauses(sent)
            lengths.append(len(sent))
            if clause_count > 1:
                clause_ratios.append(1.0)
            else:
                clause_ratios.append(0.0)
        
        avg_clause_ratio = sum(clause_ratios) / len(clause_ratios) if clause_ratios else 0.0
        
        if len(lengths) > 1:
            mean_length = sum(lengths) / len(lengths)
            variance = sum((l - mean_length) ** 2 for l in lengths) / len(lengths)
            length_variance_score = min(variance / 100.0, 1.0)
        else:
            length_variance_score = 0.0
        
        return (avg_clause_ratio + length_variance_score) / 2.0
    
    def _count_clauses(self, sentence: str) -> int:
        """分句统计（按逗号 + 顿号计数）。
        
        Args:
            sentence: 单个句子
            
        Returns:
            int: 分句数量
        """
        clause_markers = "，、"
        count = sum(sentence.count(marker) for marker in clause_markers)
        return count + 1
    
    def _calculate_subordinate_ratio(self, sentences: List[str]) -> float:
        """从属分句比例（含"因为/所以/虽然/但是/如果/那么"的句子比例）。
        
        Args:
            sentences: 句子列表
            
        Returns:
            float: 从属分句比例 (0-1)
        """
        if not sentences:
            return 0.0
        
        subordinate_markers = ["因为", "所以", "虽然", "但是", "如果", "那么", "尽管", "否则", "既然", "即使"]
        count = 0
        
        for sent in sentences:
            if any(marker in sent for marker in subordinate_markers):
                count += 1
        
        return count / len(sentences)
