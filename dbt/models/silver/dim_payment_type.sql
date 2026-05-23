-- Payment type dimension. Static lookup of the 5 AU payment types.
select * from (
    values
        ('credit_card', 'Credit Card', true),
        ('debit_card',  'Debit Card',  false),
        ('afterpay',    'Afterpay',    true),
        ('bpay',        'BPAY',        false),
        ('paypal',      'PayPal',      false)
) as t(payment_type, payment_type_label, supports_installments)
