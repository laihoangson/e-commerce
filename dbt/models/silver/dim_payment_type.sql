-- Payment type dimension. Static lookup of Olist (Brazilian) payment types.
select * from (
    values
        ('credit_card', 'Credit Card', true),
        ('boleto',      'Boleto',      false),
        ('voucher',     'Voucher',     false),
        ('debit_card',  'Debit Card',  false),
        ('not_defined', 'Not Defined', false)
) as t(payment_type, payment_type_label, supports_installments)
