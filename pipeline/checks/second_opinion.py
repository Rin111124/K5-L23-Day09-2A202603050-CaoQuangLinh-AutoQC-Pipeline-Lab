"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    so_cfg = cfg["second_opinion"]
    conf_th = so_cfg["conf"]
    min_area_px = so_cfg["min_area_px"]
    fp_conf = so_cfg["fp_conf"]
    iou_missing = so_cfg["iou_missing"]
    iou_match = so_cfg["iou_match"]
    iou_loose = so_cfg["iou_loose"]

    issues = []

    for img_p in ds.image_files():
        stem = img_p.stem
        if stem not in preds:
            continue
        if not ds.label_path(stem).exists():
            continue

        p_list = preds[stem]
        raw_lines = ds.read_label_lines(stem)

        valid_lines = []
        if raw_lines:
            for line_no, text in raw_lines:
                try:
                    c, cx, cy, w, h = parse_yolo_line(text)
                except ValueError:
                    continue
                if 0 <= c < len(ds.classes):
                    valid_lines.append((line_no, c, (cx, cy, w, h)))

        labels_list = [(c, box) for _, c, box in valid_lines]

        im_size = ds.image_size(stem)
        W, H = im_size if im_size else (1, 1)

        # 1. Filter predictions P (conf >= conf_th and area >= min_area_px)
        P = []
        for p in p_list:
            c, conf, pcx, pcy, pw, ph = p
            area = (pw * W) * (ph * H)
            if conf >= conf_th and area >= min_area_px:
                P.append(p)

        # 2. Evaluate predictions in order
        for p in P:
            p_cls, p_conf, pcx, pcy, pw, ph = p
            p_box = (pcx, pcy, pw, ph)

            cands = []
            for l_cls, l_box in labels_list:
                iou = iou_xywh(p_box, l_box)
                if iou >= iou_missing:
                    cands.append((l_cls, l_box, iou))

            if not cands:
                issues.append(Issue(
                    "second_opinion", WARN, "POSSIBLE_MISSING", stem,
                    f"model dự đoán {ds.classes[p_cls]} (conf={p_conf:.2f}) nhưng nhãn thiếu box",
                    line=None, extra={"conf": p_conf, "cls": p_cls}
                ))
            else:
                same_class_cands = [iou for l_cls, _, iou in cands if l_cls == p_cls]
                if same_class_cands:
                    best_same = max(same_class_cands)
                    if best_same < iou_loose:
                        issues.append(Issue(
                            "second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                            f"nhãn {ds.classes[p_cls]} khớp vật nhưng box lỏng (IoU={best_same:.2f} < {iou_loose})",
                            line=None, extra={"iou": best_same, "conf": p_conf}
                        ))
                    # else: covered correctly by same class label -> no issue
                else:
                    best_other = max(iou for _, _, iou in cands)
                    if best_other >= iou_match:
                        issues.append(Issue(
                            "second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                            f"model dự đoán {ds.classes[p_cls]} (conf={p_conf:.2f}), nhãn gán khác lớp với IoU={best_other:.2f}",
                            line=None, extra={"iou": best_other, "conf": p_conf}
                        ))
                    # else: ambiguous IoU in [iou_missing, iou_match) -> no issue

        # 3. False Positive check for each valid label line
        P_fp = [p for p in p_list if p[1] >= fp_conf]
        for line_no, l_cls, l_box in valid_lines:
            max_iou = 0.0
            for p in P_fp:
                p_box = (p[2], p[3], p[4], p[5])
                iou = iou_xywh(l_box, p_box)
                if iou > max_iou:
                    max_iou = iou
            if max_iou < iou_missing:
                issues.append(Issue(
                    "second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                    f"dòng {line_no}: box nhãn không khớp dự đoán nào (max IoU={max_iou:.2f} < {iou_missing})",
                    line=line_no, extra={"max_iou": max_iou}
                ))

    return issues
