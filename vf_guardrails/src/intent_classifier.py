import json
import os
import sys
import numpy as np
import ahocorasick

class IntentClassifier:
    def __init__(self, keywords_path: str):
        self.keywords_path = keywords_path
        self.automaton = ahocorasick.Automaton()
        self.intents_config = {}
        self.model_loaded = False
        
        # Biến cho tầng ONNX Semantic Fallback
        self.tokenizer = None
        self.ort_session = None
        self.anchor_embeddings = {}  # Lưu trữ intent -> np.ndarray chứa các anchor embeddings
        
        # 1. Nạp từ khóa cho Tầng 1
        self._load_keywords()
        
        # 2. Cố gắng tải mô hình ONNX cho Tầng 2
        self._load_onnx_model()

    def _load_keywords(self):
        if not os.path.exists(self.keywords_path):
            raise FileNotFoundError(f"Keywords config file not found: {self.keywords_path}")
            
        with open(self.keywords_path, 'r', encoding='utf-8') as f:
            self.intents_config = json.load(f)
            
        # Đăng ký từ khóa hành động và thực thể vào cây Aho-Corasick
        # pyahocorasick sẽ ghi đè giá trị nếu add_word trùng từ khóa.
        # Do đó ta lưu danh sách tuple (type, word, intent) cho mỗi từ khóa.
        for intent_name, data in self.intents_config.items():
            actions = data.get("actions", [])
            entities = data.get("entities", [])
            
            for act in actions:
                clean_act = act.strip().lower()
                if clean_act:
                    if clean_act in self.automaton:
                        self.automaton.get(clean_act).append(("action", clean_act, intent_name))
                    else:
                        self.automaton.add_word(clean_act, [("action", clean_act, intent_name)])
            for ent in entities:
                clean_ent = ent.strip().lower()
                if clean_ent:
                    if clean_ent in self.automaton:
                        self.automaton.get(clean_ent).append(("entity", clean_ent, intent_name))
                    else:
                        self.automaton.add_word(clean_ent, [("entity", clean_ent, intent_name)])
                    
        self.automaton.make_automaton()

    def _load_onnx_model(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_dir = os.path.join(base_dir, "model")
        onnx_path = os.path.join(model_dir, "model.onnx")
        
        if not os.path.exists(onnx_path):
            print(f"\n[Warning] ONNX model not found at {onnx_path}. Semantic fallback is disabled.")
            print("Please run 'python setup_model.py' to download the model.")
            return

        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer
            
            # Nạp Tokenizer ngoại tuyến
            self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
            # Khởi tạo ONNX session
            self.ort_session = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
            self.model_loaded = True
            
            # Tính toán trước embedding cho các anchor queries để tăng tốc tối đa
            self._precompute_anchor_embeddings()
            print("PhoBERT Semantic Fallback initialized successfully.")
        except Exception as e:
            print(f"\n[Warning] Failed to initialize ONNX Semantic Fallback: {e}")
            self.model_loaded = False

    def _get_embedding(self, text: str) -> np.ndarray:
        """Sinh embedding vector 768-D từ một câu văn sử dụng PhoBERT ONNX và Mean Pooling"""
        from pyvi import ViTokenizer
        
        # 1. Tách từ tiếng Việt sử dụng thư viện pyvi
        segmented_text = ViTokenizer.tokenize(text)
        
        # 2. Mã hóa chuỗi đầu vào
        encoded = self.tokenizer(segmented_text, return_tensors="np", padding=True, truncation=True)
        
        # 3. Chuẩn bị dữ liệu đầu vào cho ONNX
        input_names = [x.name for x in self.ort_session.get_inputs()]
        feed_dict = {}
        for name in input_names:
            if name in encoded:
                feed_dict[name] = encoded[name]
            elif name == "token_type_ids":
                feed_dict[name] = np.zeros_like(encoded["input_ids"])
                
        # 4. Chạy mô hình
        outputs = self.ort_session.run(None, feed_dict)
        last_hidden_state = outputs[0]  # Shape: (1, sequence_length, 768)
        
        # 5. Thực hiện Mean Pooling (bỏ qua các token đệm padding)
        attention_mask = encoded["attention_mask"]  # Shape: (1, sequence_length)
        input_mask_expanded = np.expand_dims(attention_mask, axis=-1)
        sum_embeddings = np.sum(last_hidden_state * input_mask_expanded, axis=1)
        sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        
        sentence_embedding = sum_embeddings / sum_mask  # Shape: (1, 768)
        
        # 6. L2 Normalization
        norm = np.linalg.norm(sentence_embedding, axis=1, keepdims=True)
        normalized_emb = sentence_embedding / np.clip(norm, a_min=1e-9, a_max=None)
        
        return normalized_emb[0]

    def _precompute_anchor_embeddings(self):
        """Tính toán sẵn và cache các embedding vector của anchor queries lúc khởi động"""
        for intent_name, data in self.intents_config.items():
            anchors = data.get("anchors", [])
            embeddings = []
            for anchor in anchors:
                try:
                    emb = self._get_embedding(anchor)
                    embeddings.append(emb)
                except Exception as e:
                    print(f"[Warning] Failed to compute embedding for anchor '{anchor}': {e}")
            if embeddings:
                self.anchor_embeddings[intent_name] = np.array(embeddings)  # Shape: (num_anchors, 768)

    def _classify_level1(self, query: str) -> str:
        """Tầng 1: Khớp kết hợp Action + Entity bằng Aho-Corasick"""
        normalized_query = query.strip().lower()
        
        # 1. Tìm các từ khóa khớp
        matches = []
        for end_idx, payload_list in self.automaton.iter(normalized_query):
            for kw_type, kw, intent in payload_list:
                matches.append((kw_type, kw, intent))
            
        if not matches:
            return None
            
        # 2. Nhóm từ khóa khớp theo intent
        intent_matches = {}
        for kw_type, kw, intent in matches:
            if intent not in intent_matches:
                intent_matches[intent] = {"actions": [], "entities": []}
            if kw_type == "action":
                intent_matches[intent]["actions"].append(kw)
            elif kw_type == "entity":
                intent_matches[intent]["entities"].append(kw)
                
        # 3. Đánh giá xem intent nào khớp cả Action lẫn Entity
        valid_intents = []
        for intent_name, matched_data in intent_matches.items():
            if matched_data["actions"] and matched_data["entities"]:
                # Điểm số = tổng độ dài các từ khóa khớp để ưu tiên từ khóa dài nhất
                score = sum(len(a) for a in matched_data["actions"]) + sum(len(e) for e in matched_data["entities"])
                valid_intents.append((intent_name, score))
                
        if not valid_intents:
            return None
            
        # Sắp xếp theo điểm số xếp hạng giảm dần
        valid_intents.sort(key=lambda x: x[1], reverse=True)
        return valid_intents[0][0]

    def _classify_level2(self, query: str) -> str:
        """Tầng 2: So khớp ngữ nghĩa dựa trên PhoBERT ONNX Cosine Similarity"""
        if not self.model_loaded or not self.anchor_embeddings:
            return "INTENT_UNKNOWN"
            
        try:
            # 1. Tính embedding cho query
            query_emb = self._get_embedding(query)  # Shape: (768,)
            
            best_intent = "INTENT_UNKNOWN"
            best_score = -1.0
            
            # Ngưỡng tin cậy cho tương đồng ngữ nghĩa
            threshold = 0.65
            
            # 2. Duyệt qua từng intent và tính độ tương đồng với các anchors của nó
            for intent_name, anchor_embs in self.anchor_embeddings.items():
                # anchor_embs shape: (num_anchors, 768)
                # Tính Cosine Similarity bằng dot product (do các vector đã được L2 normalized)
                similarities = np.dot(anchor_embs, query_emb)  # Shape: (num_anchors,)
                max_similarity = float(np.max(similarities))
                
                if max_similarity > best_score:
                    best_score = max_similarity
                    best_intent = intent_name
            
            if best_score >= threshold:
                return best_intent
            else:
                return "INTENT_UNKNOWN"
                
        except Exception as e:
            print(f"[Warning] Error during Semantic Fallback inference: {e}")
            return "INTENT_UNKNOWN"

    def classify(self, query: str) -> str:
        if not query:
            return "INTENT_UNKNOWN"
            
        # Tầng 1: Aho-Corasick (Action + Entity)
        intent = self._classify_level1(query)
        if intent:
            return intent
            
        # Tầng 2: Semantic Fallback ONNX
        return self._classify_level2(query)
