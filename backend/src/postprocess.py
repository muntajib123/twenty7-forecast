# backend/src/postprocess.py
from typing import Any, Dict, Optional

def kp_to_ap_integer(kp: Optional[float]) -> Optional[int]:
    """Standard NOAA integer mapping for Kp -> Ap (returns integer Ap or None)."""
    if kp is None:
        return None
    try:
        k = int(round(float(kp)))
    except Exception:
        return None
    mapping = {0:0,1:3,2:7,3:15,4:27,5:48,6:80,7:140,8:240,9:400}
    k = max(0, min(9, k))
    return mapping.get(k, None)

def normalize_ap_from_kp(payload: Dict[str, Any], tolerance: float = 40.0) -> Dict[str, Any]:
    """
    Ensure payload['ap_horizon'] aligns with payload['horizon'] (kp predictions).
    - If ap_horizon missing or inconsistent (|ap - mapped_ap| > tolerance) we replace with mapped Ap.
    - Otherwise we keep original ap_horizon but normalize types to floats.
    """
    if payload is None:
        return payload

    kp_arr = payload.get("horizon") or payload.get("kp_horizon") or []
    ap_arr = payload.get("ap_horizon") or []

    # Build derived ap list from kp_arr
    derived = []
    for kp in kp_arr:
        mapped = kp_to_ap_integer(kp)
        derived.append(mapped)

    # Decide whether to use derived list
    use_derived = False
    if not ap_arr or len(ap_arr) != len(derived):
        use_derived = True
    else:
        for a, d in zip(ap_arr, derived):
            try:
                a_num = float(a) if a is not None else None
            except Exception:
                a_num = None
            if d is None:
                continue
            if a_num is None or abs(a_num - float(d)) > tolerance:
                use_derived = True
                break

    if use_derived:
        payload["ap_horizon"] = [float(x) if x is not None else 0.0 for x in derived]
    else:
        payload["ap_horizon"] = [float(x) if x is not None else 0.0 for x in ap_arr]

    return payload
