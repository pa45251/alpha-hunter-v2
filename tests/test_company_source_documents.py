import pytest
from company_source_documents import verify_document_claim


def docs():
    return {'https://issuer.example/product': dict(ticker='1234.TW',fetch_status='FETCHED',document_text='Our NAND storage controllers supply industrial SSD products and shipments rose 20 percent.')}


def test_exact_company_quote_required():
    e=dict(ticker='1234.TW',source_url='https://issuer.example/product',source_quote='Our NAND storage controllers supply industrial SSD products')
    verify_document_claim(e,docs(),specific=True)
    with pytest.raises(ValueError,match='QUOTE'):
        verify_document_claim(dict(e,source_quote='AI orders have doubled this month'),docs())


def test_macro_or_other_company_cannot_substitute():
    e=dict(ticker='OTHER.TW',source_url='https://issuer.example/product',source_quote='Our NAND storage controllers supply industrial SSD products')
    with pytest.raises(ValueError,match='SCOPE'):
        verify_document_claim(e,docs())
    with pytest.raises(ValueError,match='UNFETCHED'):
        verify_document_claim(dict(e,source_url='https://macro.example/industry'),docs())


def test_generic_revenue_is_not_specific_driver():
    d=docs();d['https://issuer.example/product']['evidence_role']='GENERIC_REVENUE_ONLY'
    e=dict(ticker='1234.TW',source_url='https://issuer.example/product',source_quote='Our NAND storage controllers supply industrial SSD products')
    with pytest.raises(ValueError,match='GENERIC_REVENUE'):
        verify_document_claim(e,d,specific=True)
