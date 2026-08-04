import json, re
with open('evaluation/golden_set.json', encoding='utf-8') as f:
    items = json.load(f)
for it in items:
    if it.get('id') in {5} or it.get('id') is None:
        ans = it.get('expected_answer', '')
        ctx = it.get('ground_truth_context', '')
        q = it.get('question', '')
        ans_w = set(re.findall(r'\w+', ans.lower()))
        ctx_w = set(re.findall(r'\w+', ctx.lower()))
        ratio = len(ans_w & ctx_w)/len(ans_w) if ans_w else 0
        print(f"id={it.get('id')} type={it.get('type')} overlap={ratio:.3f}")
        print(f"Q: {q[:100]}")
        print(f"A: {ans[:250]}")
        print(f"CTX: {ctx[:150]}")
        print()
