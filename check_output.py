import csv

rows = list(csv.DictReader(open('output.csv')))
print('output rows:', len(rows))
cols = list(rows[0].keys()) if rows else []
print('columns:', cols)

# check amount bounds
reqs = {r['request_id']: float(r['requested_amount']) for r in csv.DictReader(open('dataset/requests.csv'))}
req_dates = {r['request_id']: r['request_date'] for r in csv.DictReader(open('dataset/requests.csv'))}
req_ids = set(reqs.keys())

# 1. All request_ids covered?
out_ids = {r['request_id'] for r in rows}
missing = req_ids - out_ids
print('missing request_ids:', len(missing), list(missing)[:3])

# 2. amount bounds
issues = []
for r in rows:
    safe = float(r['amount_safe_to_pay'])
    req_amt = reqs.get(r['request_id'], 0)
    if not (0 <= safe <= req_amt + 1e-6):
        issues.append((r['request_id'], safe, req_amt))
print('amount bound violations:', len(issues))
for i in issues[:5]:
    print(' ', i)

# 3. affordability_status values
valid_status = {'affordable_now', 'affordable_with_plan', 'affordable_later', 'not_affordable'}
bad_status = [r['request_id'] for r in rows if r['affordability_status'] not in valid_status]
print('bad affordability_status:', len(bad_status), bad_status[:3])

# 4. method values
valid_methods = {'full_payment', 'partial_payment', 'installments', 'wait', 'not_recommended'}
bad_methods = [r['request_id'] for r in rows if r['recommended_payment_method'] not in valid_methods]
print('bad methods:', len(bad_methods), bad_methods[:3])

# 5. affordable_now must have earliest == request_date
mismatch = []
for r in rows:
    if r['affordability_status'] == 'affordable_now':
        if r['earliest_date_for_full_payment'] != req_dates.get(r['request_id'], ''):
            mismatch.append((r['request_id'], r['earliest_date_for_full_payment'], req_dates.get(r['request_id'])))
print('affordable_now earliest!=request_date:', len(mismatch))
for m in mismatch[:5]:
    print(' ', m)

# 6. Column order check
required_order = ['request_id', 'amount_safe_to_pay', 'affordability_status',
                  'recommended_payment_method', 'payment_plan',
                  'earliest_date_for_full_payment', 'spending_changes_needed', 'decision_explanation']
print('column order correct:', cols == required_order)

# 7. partial_payment sanity check
for r in rows:
    if r['recommended_payment_method'] == 'partial_payment':
        plan = r['payment_plan']
        parts = plan.split('|')
        req_id = r['request_id']
        req_amt = reqs.get(req_id, 0)
        safe = float(r['amount_safe_to_pay'])
        if len(parts) != 2:
            print(f'  PARTIAL plan not 2 payments: {req_id} -> {plan}')
        else:
            d1, a1 = parts[0].split(':')
            d2, a2 = parts[1].split(':')
            total = float(a1) + float(a2)
            if abs(total - req_amt) > 0.02:
                print(f'  PARTIAL sum mismatch: {req_id} total={total} req={req_amt}')

print('Checks done.')
