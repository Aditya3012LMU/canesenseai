"""
CANESENSE NIR — Payment Calculator
Implements the sugarcane fair-price payment formula.

Formula:
    Payment = W × P_b × (Pol / Pol_std) × Q_f
    Q_f     = 1 − α × (ADF − ADF_std)
"""


def calculate_quality_factor(adf_avg: float, adf_std: float, alpha: float) -> float:
    """
    Q_f = 1 - α × (ADF_avg - ADF_std)
    A higher fiber content than standard reduces the quality factor (penalty).
    """
    q_f = 1.0 - alpha * (adf_avg - adf_std)
    return round(q_f, 6)


def calculate_payment(
    weight:     float,    # W   — cane weight delivered (tons)
    base_price: float,    # P_b — base price per ton (currency)
    pol_avg:    float,    # Pol — predicted average sucrose %
    pol_std:    float,    # Pol_std — industry standard sucrose %
    adf_avg:    float,    # ADF — predicted average fiber %
    adf_std:    float,    # ADF_std — standard fiber %
    alpha:      float,    # α   — fiber penalty factor
) -> dict:
    """
    Returns a breakdown dict with Q_f, Pol ratio, and final payment.
    """
    if pol_std <= 0:
        return {'error': 'pol_std must be greater than zero'}

    q_f       = calculate_quality_factor(adf_avg, adf_std, alpha)
    pol_ratio = pol_avg / pol_std
    payment   = weight * base_price * pol_ratio * q_f

    return {
        'weight':       round(weight,     2),
        'base_price':   round(base_price, 2),
        'pol_avg':      round(pol_avg,    3),
        'pol_std':      round(pol_std,    3),
        'pol_ratio':    round(pol_ratio,  4),
        'adf_avg':      round(adf_avg,    3),
        'adf_std':      round(adf_std,    3),
        'alpha':        round(alpha,      4),
        'quality_factor': round(q_f,      4),
        'payment':      round(payment,    2),
    }


def batch_payment_report(farmers: list, params: dict) -> list:
    """
    farmers : list of dicts with farmer_id, farmer_name, predicted_pol,
              average_ADF, weight (optional)
    params  : dict with base_price, pol_std, adf_std, alpha, default_weight
    """
    report = []
    for f in farmers:
        weight = f.get('weight', params.get('default_weight', 10.0))
        result = calculate_payment(
            weight     = float(weight),
            base_price = float(params['base_price']),
            pol_avg    = float(f.get('predicted_pol', 0)),
            pol_std    = float(params['pol_std']),
            adf_avg    = float(f.get('average_ADF', 0)),
            adf_std    = float(params['adf_std']),
            alpha      = float(params['alpha']),
        )
        report.append({
            'farmer_id':      f.get('farmer_id', '-'),
            'farmer_name':    f.get('farmer_name', 'Unknown'),
            'samples_scanned': f.get('samples_scanned', 0),
            **result,
        })
    return report
