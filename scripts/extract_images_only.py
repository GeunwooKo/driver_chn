import sys, json, os
sys.path.insert(0, os.path.dirname(__file__))
import extract_pipeline as P

doc = P.doc
N = len(doc)
print(f'Total pages: {N}', flush=True)

all_lines = []
for pi in range(0, N):
    page = doc[pi]
    rect = page.rect
    mid = rect.width / 2
    all_lines.extend(P.process_half(page, 0, mid, f'p{pi}_L', page_idx=pi))
    all_lines.extend(P.process_half(page, mid, rect.width, f'p{pi}_R', page_idx=pi))
    print(f'page {pi} done', flush=True)

qs = P.build_questions(all_lines)
P.assign_images(qs)
print(f'Total questions parsed (OCR pass, for image association only): {len(qs)}', flush=True)

os.makedirs('/Volumes/P31/driver_agent/images', exist_ok=True)

mapping = {}
count = 0
for q in qs:
    if not q.get('_blob'):
        continue
    page_idx = P.col_registry[q['_col_key']]['page_idx']
    key = f"{page_idx}:{q['number']}"
    count += 1
    img_name = f'q_{page_idx:02d}_{q["number"]:04d}_{count:04d}.jpg'
    out_path = f'/Volumes/P31/driver_agent/images/{img_name}'
    saved = P.save_question_image(q, out_path)
    if saved:
        # a given (page,number) could collide if numbering repeats within a page (rare);
        # keep a list to allow disambiguation later.
        mapping.setdefault(key, []).append(f'images/{img_name}')

with open('/Volumes/P31/driver_agent/_agent_out/image_map.json', 'w', encoding='utf-8') as f:
    json.dump(mapping, f, ensure_ascii=False, indent=1)

print(f'Saved {count} native-resolution images, wrote image_map.json with {len(mapping)} keys', flush=True)
