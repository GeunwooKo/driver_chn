import fitz, numpy as np, subprocess, re, json, os, sys
from scipy import ndimage
from PIL import Image, ImageDraw

PDF = '/Volumes/P31/driver_agent/chn_driver.pdf'
SCALE = 8.0
OUT_IMG_DIR = '/Volumes/P31/driver_agent/images'
TMP_DIR = '/Volumes/P31/driver_agent/_tmp_ocr'
os.makedirs(OUT_IMG_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

doc = fitz.open(PDF)

QNUM_RE = re.compile(r'^\s*(\d{1,4})\s*[.。]\s*(.*)$')
OPT_RE = re.compile(r'^\s*\S{1,3}\s*[:：]\s*(.*)$')
FOOTER_RE = re.compile(r'(第|共|页|CHINA|版权|DRIVE)')

def detect_blobs(arr, scale):
    gray = arr[:,:,:3].mean(axis=2)
    nonwhite = gray < 245
    density = ndimage.uniform_filter(nonwhite.astype(np.float32), size=int(25*scale/3))
    photo_mask = density > 0.55
    lbl, n = ndimage.label(photo_mask)
    objs = ndimage.find_objects(lbl)
    boxes = []
    min_area = (scale*scale)*300
    for sl in objs:
        y0,y1 = sl[0].start, sl[0].stop
        x0,x1 = sl[1].start, sl[1].stop
        area = (y1-y0)*(x1-x0)
        w = x1-x0; h = y1-y0
        if area > min_area and w > 15*scale and h > 15*scale:
            boxes.append((x0,y0,x1,y1))
    return boxes

def find_gutter(arr, w):
    gray = arr[:,:,:3].mean(axis=2)
    nonwhite = (gray < 245).sum(axis=0)
    lo, hi = int(w*0.15), int(w*0.85)
    thresh = max(15, int(w*0.002))
    zero = nonwhite[lo:hi] <= thresh
    runs = []
    start = None
    for i, v in enumerate(zero):
        if v and start is None: start = i
        if not v and start is not None:
            runs.append((start, i)); start = None
    if start is not None: runs.append((start, len(zero)))
    runs = [r for r in runs if (r[1]-r[0]) > 5]
    if not runs:
        return w // 2
    center_target = (hi-lo)/2
    runs.sort(key=lambda r: abs(((r[0]+r[1])/2) - center_target))
    best = runs[0]
    return lo + (best[0]+best[1])//2

def ocr_tsv(png_path, tag, lang='kor+eng', psm='6'):
    tsv_base = f'{TMP_DIR}/{tag}'
    cmd = ['tesseract', png_path, tsv_base, '-l', lang, '--psm', psm, 'tsv']
    subprocess.run(cmd, capture_output=True, text=True)
    return tsv_base + '.tsv'

def parse_tsv_lines(tsv_path):
    lines_data = {}
    with open(tsv_path, encoding='utf-8') as f:
        header = f.readline().strip().split('\t')
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) != len(header):
                continue
            rec = dict(zip(header, parts))
            if rec['text'].strip() == '':
                continue
            key = (int(rec['block_num']), int(rec['par_num']), int(rec['line_num']))
            lines_data.setdefault(key, []).append(rec)
    line_list = []
    for key in sorted(lines_data.keys()):
        words = lines_data[key]
        text = ' '.join(w['text'] for w in words)
        left = min(int(w['left']) for w in words)
        top = min(int(w['top']) for w in words)
        right = max(int(w['left'])+int(w['width']) for w in words)
        bottom = max(int(w['top'])+int(w['height']) for w in words)
        line_list.append({'text': text, 'left': left, 'top': top, 'right': right, 'bottom': bottom})
    return line_list

def is_red_line(arr, left, top, right, bottom):
    h, w = arr.shape[:2]
    top = max(0,top); bottom=min(h,bottom); left=max(0,left); right=min(w,right)
    if bottom<=top or right<=left:
        return False
    region = arr[top:bottom, left:right, :3]
    mask = ~np.all(region > 240, axis=-1)
    if mask.sum() < 5:
        return False
    px = region[mask]
    mean = px.mean(axis=0)
    return (mean[0] - mean[1]) > 40 and (mean[0] - mean[2]) > 40

def ocr_answer_letter(col_img, left, top, right, bottom, tag):
    pad = 8
    crop = col_img.crop((max(0,left-pad), max(0,top-pad), right+pad, bottom+pad))
    png_path = f'{TMP_DIR}/{tag}_ans.png'
    crop.save(png_path)
    txt = subprocess.run(['tesseract', png_path, 'stdout', '-l', 'chi_sim+eng', '--psm', '7'],
                          capture_output=True, text=True).stdout
    m = re.findall(r'[A-DYN]', txt.upper())
    if m:
        return m[-1]
    return None

# ---- global registries ----
col_registry = {}   # col_key -> {'img': PIL image, 'boxes': [local blob boxes]}
flat_lines = []      # ordered list across whole doc: dict(text,is_answer,answer_letter,top,left,right,bottom,col_key)

def process_column(page, x0pt, x1pt, col_key, full_arr, full_img, xoff_px):
    """x range given in local-to-half pixel coords; full_arr/full_img are the half-page render."""
    col_img = full_img.crop((x0pt, 0, x1pt, full_img.height))
    local_boxes_all = col_registry[col_key]['boxes']

    ocr_img = col_img.copy()
    draw = ImageDraw.Draw(ocr_img)
    pad = 6
    for (bx0,by0,bx1,by1) in local_boxes_all:
        draw.rectangle([bx0-pad,by0-pad,bx1+pad,by1+pad], fill=(255,255,255))
    png_path = f'{TMP_DIR}/{col_key}_ocr.png'
    ocr_img.save(png_path)
    tsv_path = ocr_tsv(png_path, col_key)
    lines = parse_tsv_lines(tsv_path)

    arr = np.array(col_img.convert('RGB'))
    for ln in lines:
        if FOOTER_RE.search(ln['text']):
            ln['skip'] = True
            continue
        ln['skip'] = False
        ln['is_answer'] = is_red_line(arr, ln['left'], ln['top'], ln['right'], ln['bottom'])
        ln['answer_letter'] = None
        if ln['is_answer']:
            ln['answer_letter'] = ocr_answer_letter(col_img, ln['left'], ln['top'], ln['right'], ln['bottom'], col_key+f"_{ln['top']}")
        ln['col_key'] = col_key

    lines = [l for l in lines if not l['skip']]
    col_registry[col_key]['img'] = col_img
    return lines

def process_half(page, half_x0, half_x1, tag, page_idx=None):
    rect = page.rect
    clip = fitz.Rect(half_x0, 0, half_x1, rect.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(SCALE, SCALE), clip=clip)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
    img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)

    boxes = detect_blobs(arr, SCALE)
    gutter = find_gutter(arr, pix.width)

    out_lines = []
    for ci, (x0,x1) in enumerate([(0,gutter), (gutter,pix.width)]):
        col_key = f'{tag}_c{ci}'
        local_boxes = [(bx0-x0,by0,bx1-x0,by1) for (bx0,by0,bx1,by1) in boxes if bx0>=x0-5 and bx1<=x1+5]
        col_registry[col_key] = {'boxes': local_boxes, 'img': None,
                                  'half_x0_pt': half_x0, 'col_x0_px': x0, 'page_idx': page_idx}
        lines = process_column(page, x0, x1, col_key, arr, img, x0)
        out_lines.extend(lines)
    return out_lines

def blob_to_page_rect(col_key, blob):
    """Convert a blob box (local column pixel coords) to a fitz.Rect in page point space."""
    info = col_registry[col_key]
    x0,y0,x1,y1 = blob
    px0 = info['half_x0_pt'] + (info['col_x0_px'] + x0) / SCALE
    px1 = info['half_x0_pt'] + (info['col_x0_px'] + x1) / SCALE
    py0 = y0 / SCALE
    py1 = y1 / SCALE
    return fitz.Rect(px0, py0, px1, py1)

def build_questions(lines):
    questions = []
    cur = None
    for ln in lines:
        text = ln['text'].strip()
        if ln['is_answer']:
            if cur is not None and cur['answer'] is None:
                cur['answer'] = ln['answer_letter']
            continue
        m = QNUM_RE.match(text)
        if m:
            if cur is not None:
                questions.append(cur)
            cur = {'number': int(m.group(1)), 'stem_lines': [m.group(2)], 'option_lines': [],
                   'top': ln['top'], 'bottom': ln['bottom'], 'answer': None,
                   'col_key': ln['col_key']}
            continue
        if cur is None:
            continue
        om = OPT_RE.match(text)
        if om and len(cur['option_lines']) < 4:
            cur['option_lines'].append(om.group(1).strip())
        else:
            if cur['option_lines']:
                cur['option_lines'][-1] = (cur['option_lines'][-1] + ' ' + text).strip()
            else:
                cur['stem_lines'].append(text)
        if ln['col_key'] == cur['col_key']:
            cur['bottom'] = ln['bottom']
    if cur is not None:
        questions.append(cur)

    for q in questions:
        q['text'] = ' '.join(s.strip() for s in q['stem_lines'] if s.strip())
        del q['stem_lines']
    return questions

def assign_images(questions):
    # group questions by col_key of header line, in order, to compute next-boundary within same col
    from collections import defaultdict
    by_col = defaultdict(list)
    for i, q in enumerate(questions):
        by_col[q['col_key']].append(q)
    for col_key, qs in by_col.items():
        boxes = col_registry[col_key]['boxes']
        used = set()
        for i, q in enumerate(qs):
            top = q['top']
            limit = qs[i+1]['top'] if i+1 < len(qs) else 10**9
            cands = [b for b in boxes if b[1] >= top-60 and b[1] < limit and id(b) not in used]
            if cands:
                b = cands[0]
                used.add(id(b))
                q['_blob'] = b
                q['_col_key'] = col_key
            else:
                q['_blob'] = None

IMG_SCALE = 3.0  # close to native embedded-image pixel density; avoids upsample blur

def save_question_image(q, out_path):
    if not q.get('_blob'):
        return None
    col_key = q['_col_key']
    page_idx = col_registry[col_key]['page_idx']
    page = doc[page_idx]
    rect = blob_to_page_rect(col_key, q['_blob'])
    pad = 1.5  # points
    rect = fitz.Rect(rect.x0-pad, rect.y0-pad, rect.x1+pad, rect.y1+pad)
    pix = page.get_pixmap(matrix=fitz.Matrix(IMG_SCALE, IMG_SCALE), clip=rect)
    img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    img.save(out_path, quality=92)
    return out_path

if __name__ == '__main__':
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 49
    end = int(sys.argv[2]) if len(sys.argv) > 2 else start
    all_lines = []
    for pi in range(start, end+1):
        page = doc[pi]
        rect = page.rect
        mid = rect.width/2
        all_lines.extend(process_half(page, 0, mid, f'p{pi}_L', page_idx=pi))
        all_lines.extend(process_half(page, mid, rect.width, f'p{pi}_R', page_idx=pi))
    qs = build_questions(all_lines)
    assign_images(qs)
    for q in qs:
        print(q['number'], '|', q['text'][:60], '|', q['option_lines'], '|', q['answer'], 'IMG' if q['_blob'] else '')
