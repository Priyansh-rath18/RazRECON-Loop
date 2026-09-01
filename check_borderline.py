import json

with open('data/stage2_results.json') as f:
    stage2 = json.load(f)

borderline_ids = ['PAY-00066', 'PAY-00136', 'PAY-00190', 'PAY-00090', 'PAY-00146']

for r in stage2:
    if r['payment_id'] in borderline_ids:
        bank_status = r['bank_match']['status']
        lifecycle_status = r['lifecycle_check']['status'] if r['lifecycle_check'] else 'N/A'
        is_clean = bank_status == 'MATCHED' and lifecycle_status == 'PASS'
        outcome = 'CLEAN (missed)' if is_clean else 'EXCEPTION (caught)'
        print(f"{r['payment_id']}: bank={bank_status}, lifecycle={lifecycle_status} -> {outcome}")