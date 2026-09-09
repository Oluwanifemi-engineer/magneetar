"""
Business & Payments Domain

Owns: Subscription management, payment processing, plan enforcement,
      device limits per plan, billing events.

Data tables: payments, subscriptions
Extracted from: routes/payments.py

Domain Events Published:
  - payment_completed      {user_id, amount, currency, plan}
  - payment_failed         {user_id, reason, retryable}
  - subscription_activated {user_id, plan, device_limit}
  - subscription_expired   {user_id, plan}
  - device_limit_reached   {user_id, current_count, max_allowed}
"""
