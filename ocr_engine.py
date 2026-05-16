import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


class OCREngine:
    def __init__(self):
        self._ocr = None

    def _init_ocr(self):
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(
            lang='ch',
            use_angle_cls=True,
            use_gpu=False,
            show_log=False,
            det_db_thresh=0.3,
            rec_batch_num=6,
        )

    def preprocess(self, image):
        gray = image.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        high_contrast = enhancer.enhance(2.0)
        sharpened = high_contrast.filter(ImageFilter.SHARPEN)
        return sharpened

    def recognize(self, image):
        if self._ocr is None:
            self._init_ocr()
        processed = self.preprocess(image)
        raw = self._ocr.ocr(np.array(processed), cls=True)
        return self._format_results(raw)

    def _format_results(self, raw_results):
        items = []
        if raw_results and raw_results[0]:
            for line in raw_results[0]:
                bbox, (text, conf) = line
                y_center = (bbox[0][1] + bbox[2][1]) / 2
                items.append({
                    'text': text.strip(),
                    'confidence': conf,
                    'bbox': bbox,
                    'y_center': y_center,
                })
        items.sort(key=lambda x: x['y_center'])
        return items
