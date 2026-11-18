"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}


def fix(ds, issues, cfg):
    fixes = []
    error_issues = [i for i in issues if i.severity == ERROR]

    # 1. Image removals
    removed_images = set()
    for i in error_issues:
        if i.code.startswith("DUP_IMAGE_") or i.code in REMOVE_CODES:
            stem = i.image
            if stem not in removed_images:
                removed_images.add(stem)
                # Xoá ảnh
                img_p = ds.image_path(stem)
                if img_p and img_p.exists():
                    img_p.unlink()
                # Xoá nhãn nếu có
                lbl_p = ds.label_path(stem)
                if lbl_p and lbl_p.exists():
                    lbl_p.unlink()
                ds._size_cache.pop(stem, None)
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "remove_image",
                    "before": i.code,
                    "after": "(đã xoá)",
                })

    # 2. Rename classes in data.yaml
    for i in error_issues:
        if i.code == "BAD_CLASS_NAME":
            old_names = ds.yaml_names()
            d = {}
            if ds.yaml_path.exists():
                try:
                    d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    d = {}
            d["names"] = list(cfg["classes"])
            ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": str(old_names),
                "after": str(cfg["classes"]),
            })
            break

    # 3. Missing label files (chuyển người gán, không tạo file)
    missing_seen = set()
    for i in error_issues:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed_images:
            if i.image not in missing_seen:
                missing_seen.add(i.image)
                fixes.append({
                    "image": i.image,
                    "line": "",
                    "action": "needs_label",
                    "before": "(không có file)",
                    "after": "chuyển người gán",
                })

    # 4. Line-level fixes in label files
    issues_by_image = defaultdict(list)
    for i in error_issues:
        if i.image in removed_images or i.image in missing_seen or i.image in ("data.yaml", "<dataset>"):
            continue
        if i.line is not None:
            issues_by_image[i.image].append(i)

    for stem, img_issues in issues_by_image.items():
        lbl_p = ds.label_path(stem)
        if not lbl_p.exists():
            continue

        raw_lines = lbl_p.read_text(encoding="utf-8", errors="replace").splitlines()
        to_drop = set()
        to_replace = {}  # line_no -> new_line_str

        # Group by line
        line_issues = defaultdict(list)
        for iss in img_issues:
            line_issues[iss.line].append(iss)

        for line_no in sorted(line_issues):
            if line_no < 1 or line_no > len(raw_lines):
                continue
            orig_line = raw_lines[line_no - 1]
            codes = {iss.code for iss in line_issues[line_no]}

            # Nếu có lỗi drop_line -> drop_line thắng
            if codes & DROP_CODES:
                to_drop.add(line_no)
                fixes.append({
                    "image": stem,
                    "line": line_no,
                    "action": "drop_line",
                    "before": orig_line,
                    "after": "",
                })
            elif "BOX_OUT_OF_IMAGE" in codes:
                try:
                    c, cx, cy, w, h = parse_yolo_line(orig_line)
                    x1 = cx - w / 2.0
                    y1 = cy - h / 2.0
                    x2 = cx + w / 2.0
                    y2 = cy + h / 2.0

                    x1_c = max(0.0, min(1.0, x1))
                    x2_c = max(0.0, min(1.0, x2))
                    y1_c = max(0.0, min(1.0, y1))
                    y2_c = max(0.0, min(1.0, y2))

                    w_c = x2_c - x1_c
                    h_c = y2_c - y1_c

                    if w_c <= 0 or h_c <= 0:
                        to_drop.add(line_no)
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "drop_line",
                            "before": orig_line,
                            "after": "",
                        })
                    else:
                        cx_c = (x1_c + x2_c) / 2.0
                        cy_c = (y1_c + y2_c) / 2.0
                        new_line = f"{c} {cx_c:.6g} {cy_c:.6g} {w_c:.6g} {h_c:.6g}"
                        to_replace[line_no] = new_line
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "clip_box",
                            "before": orig_line,
                            "after": new_line,
                        })
                except ValueError:
                    to_drop.add(line_no)
                    fixes.append({
                        "image": stem,
                        "line": line_no,
                        "action": "drop_line",
                        "before": orig_line,
                        "after": "",
                    })

        # Rewrite label file
        new_lines = []
        for idx, line_text in enumerate(raw_lines, 1):
            if idx in to_drop:
                continue
            elif idx in to_replace:
                new_lines.append(to_replace[idx])
            else:
                new_lines.append(line_text)

        content = "\n".join(new_lines) + ("\n" if new_lines else "")
        lbl_p.write_text(content, encoding="utf-8")

    return fixes
