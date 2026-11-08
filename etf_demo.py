"""Fictional portfolios and explicit synthetic cases, independent of real accounts."""
PROFILES=(
    dict(name='Demo Short-Term Bonds',risk=0,min_years=1,goals={'capital preservation':3,'long-term growth':1}),
    dict(name='Demo Conservative Mix',risk=1,min_years=3,goals={'capital preservation':2,'long-term growth':2}),
    dict(name='Demo Balanced Mix',risk=1,min_years=5,goals={'capital preservation':1,'long-term growth':3}),
    dict(name='Demo Global Equity',risk=2,min_years=7,goals={'capital preservation':0,'long-term growth':4}),
)
CASES={
    'Seven-year growth example':dict(goal='long-term growth',years=7,risk=1,loss_capacity=1,reserves_covered=True,liquidity_covered=True),
    'Two-year preservation example':dict(goal='capital preservation',years=2,risk=0,loss_capacity=0,reserves_covered=True,liquidity_covered=True),
}


def demo_fit(case_name):
    case=CASES[case_name];eligible=[];excluded=[]
    for order,p in enumerate(PROFILES):
        reasons=[]
        if p['min_years']>case['years']:reasons.append('Its assumed minimum horizon exceeds the example horizon.')
        if p['risk']>min(case['risk'],case['loss_capacity']):reasons.append('Its assumed risk exceeds the example risk or loss-capacity limit.')
        if not case['reserves_covered'] or not case['liquidity_covered']:reasons.append('The example has uncovered reserve or liquidity needs.')
        record={'name':p['name'],'why':' '.join(reasons) if reasons else f"Fits the supplied {case['years']}-year horizon and risk limits; its fictional design supports {case['goal']}.",'order':order}
        if reasons:excluded.append(record)
        else:eligible.append(record)
    eligible.sort(key=lambda p:(-PROFILES[p['order']]['goals'][case['goal']],p['order']))
    return eligible,excluded
