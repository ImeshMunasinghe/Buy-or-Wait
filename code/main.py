import os, sys, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loader, decide

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    dataset = os.path.join(os.path.dirname(here), 'dataset')
    out_path = os.path.join(os.path.dirname(here), 'output.csv')
    reqs, ctxs, opts_all, profs = loader.load_dataset(dataset)
    opts_by_req = {}
    for o in opts_all:
        opts_by_req.setdefault(o['request_id'], []).append(o)
    fields = ['request_id', 'amount_safe_to_pay', 'affordability_status',
              'recommended_payment_method', 'payment_plan',
              'earliest_date_for_full_payment', 'spending_changes_needed',
              'decision_explanation']
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in reqs:
            uid = r['user_id']
            ctx = ctxs.get(uid)
            if not ctx:
                w.writerow({'request_id': r['request_id'], 'amount_safe_to_pay': '0',
                            'affordability_status': 'not_affordable',
                            'recommended_payment_method': 'not_recommended',
                            'payment_plan': 'none',
                            'earliest_date_for_full_payment': '',
                            'spending_changes_needed': 'none',
                            'decision_explanation': 'User profile missing.'})
                continue
            opts = opts_by_req.get(r['request_id'], [])
            try:
                res = decide.decide(ctx, r, opts)
            except Exception as e:
                res = {'request_id': r['request_id'], 'amount_safe_to_pay': '0',
                       'affordability_status': 'not_affordable',
                       'recommended_payment_method': 'not_recommended',
                       'payment_plan': 'none',
                       'earliest_date_for_full_payment': '',
                       'spending_changes_needed': 'none',
                       'decision_explanation': 'Error: ' + str(e)}
            w.writerow(res)
    print('Wrote', out_path)

if __name__ == '__main__':
    main()
