"""
Аналитика стационарной системы M/M/c (однородные серверы, s=1).

Erlang C: вероятность ожидания P(W>0) и среднее ожидание в очереди E[W_q] (часы).

Интенсивности λ, μ — в заявках/час (λ суммарно по системе, μ на одного сервера).
"""
from __future__ import annotations

import math


def erlang_c_wait_metrics(
    num_servers: int,
    arrival_rate_per_hour: float,
    service_rate_per_server_per_hour: float,
) -> tuple[float, float, float]:
    """
    Возвращает (P_wait, E_Wq_hours, rho).

    rho = λ / (c·μ). При rho >= 1 стационарного режима нет: (1.0, inf, rho).
    """
    c = num_servers
    lam = arrival_rate_per_hour
    mu = service_rate_per_server_per_hour
    if c < 1 or mu <= 0 or lam <= 0:
        return float("nan"), float("nan"), float("nan")
    rho = lam / (c * mu)
    if rho >= 1.0 - 1e-15:
        return 1.0, float("inf"), rho

    a = lam / mu
    sum_before = 0.0
    for k in range(c):
        sum_before += a**k / math.factorial(k)
    denom = c * mu - lam
    tail_coef = (a**c / math.factorial(c)) * (c * mu / denom)
    inv_p0 = sum_before + tail_coef
    p0 = 1.0 / inv_p0
    p_wait = tail_coef * p0
    wq_hours = p_wait / denom
    return p_wait, wq_hours, rho
