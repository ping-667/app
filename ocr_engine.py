import numpy as np

class OCREngine:
    def __init__(self):
        self._ocr = None

    def _init_ocr(self):
        import logging
        logger = logging.getLogger(__name__)
        from paddleocr import PaddleOCR
        logger.info("正在初始化 PaddleOCR (首次加载模型，需下载或加载本地模型)...")
        try:
            self._ocr = PaddleOCR(
                lang='ch',
                use_textline_orientation=True,
                device='cpu',
                text_det_thresh=0.3,
                text_recognition_batch_size=6,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
            logger.info("PaddleOCR 初始化完成")
        except Exception as e:
            logger.error(f"PaddleOCR 初始化失败: {e}")
            raise

    def recognize(self, image):
        if self._ocr is None:
            self._init_ocr()
        raw = self._ocr.predict(np.array(image))
        return self._format_results(raw)

    def _format_results(self, raw_results):
        items = []
        for result in raw_results:
            rec_polys = result.get('rec_polys', [])
            rec_texts = result.get('rec_texts', [])
            rec_scores = result.get('rec_scores', [])
            for poly, text, score in zip(rec_polys, rec_texts, rec_scores):
                if isinstance(text, tuple):
                    text = text[0]
                y_center = (poly[0][1] + poly[2][1]) / 2
                items.append({
                    'text': text.strip(),
                    'confidence': float(score),
                    'bbox': poly,
                    'y_center': y_center,
                })
        items.sort(key=lambda x: x['y_center'])
        return items
