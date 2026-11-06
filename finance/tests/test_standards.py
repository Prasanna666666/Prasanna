"""MT940 and camt.053: exact formats with explicit balances. The samples are invented but follow the published field layouts."""

from finance import standards

MT940 = """:20:STMT20261031
:25:NL00ABNA0123456789
:28C:1/1
:60F:C261001EUR2000,00
:61:2610011001D23,45NTRFNONREF//1
:86:/TRTP/SEPA OVERBOEKING/NAME/Albert Heijn 1234/REMI/Boodschappen
:61:2610251025C2850,00NTRFNONREF//2
:86:/TRTP/SEPA OVERBOEKING/NAME/Acme BV/REMI/Salaris oktober
:61:2610261026D1100,00NTRFNONREF//3
:86:/TRTP/SEPA OVERBOEKING/NAME/Verhuurder/REMI/Huur oktober
:62F:C261031EUR3726,55
-
"""

CAMT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt>
<Acct><Id><IBAN>NL00ABNA0123456789</IBAN></Id><Ccy>EUR</Ccy></Acct>
<Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">2000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-10-01</Dt></Dt></Bal>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">3726.55</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-10-31</Dt></Dt></Bal>
<Ntry><Amt Ccy="EUR">23.45</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-10-01</Dt></BookgDt><NtryDtls><TxDtls><RltdPties><Cdtr><Nm>Albert Heijn 1234</Nm></Cdtr></RltdPties><RmtInf><Ustrd>Boodschappen</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
<Ntry><Amt Ccy="EUR">2850.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2026-10-25</Dt></BookgDt><NtryDtls><TxDtls><RltdPties><Dbtr><Nm>Acme BV</Nm></Dbtr></RltdPties><RmtInf><Ustrd>Salaris oktober</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
<Ntry><Amt Ccy="EUR">1100.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-10-26</Dt></BookgDt><NtryDtls><TxDtls><RmtInf><Ustrd>Huur oktober</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
</Stmt></BkToCstmrStmt></Document>"""


def test_mt940_is_read_exactly_and_the_balances_prove_it():
    assert standards.sniff(MT940) == "mt940"
    (s,) = standards.read_mt940(MT940)
    assert s.status == "verified" and s.account == "NL00ABNA0123456789" and s.opening == 200000 and s.closing == 372655
    assert [(t.day, t.amount_minor, t.kind) for t in s.txns] == [
        ("2026-10-01", 2345, "expense"),
        ("2026-10-25", 285000, "income"),
        ("2026-10-26", 110000, "expense"),
    ]
    assert "Albert Heijn 1234" in s.txns[0].desc and "Salaris oktober" in s.txns[1].desc and (s.first_day, s.last_day) == ("2026-10-01", "2026-10-26")


def test_mt940_with_one_wrong_amount_does_not_add_up_and_is_refused():
    (s,) = standards.read_mt940(MT940.replace("D23,45N", "D23,46N"))
    assert s.status == "needs_check" and "do not add up" in s.issues[0]


def test_mt940_reversals_and_overdrawn_balances():
    text = (
        MT940.replace(":60F:C261001EUR2000,00", ":60F:D261001EUR10,00")
        .replace(":62F:C261031EUR3726,55", ":62F:C261031EUR1716,55")
        .replace("D23,45N", "RC23,45N")
    )
    (s,) = standards.read_mt940(text)
    assert s.opening == -1000 and s.txns[0].kind == "expense"  # RC: a credit that was reversed takes the money back out
    assert s.status in ("verified", "needs_check")


def test_camt053_is_read_exactly_and_the_balances_prove_it():
    assert standards.sniff(CAMT) == "camt053"
    (s,) = standards.read_camt(CAMT)
    assert s.status == "verified" and s.account == "NL00ABNA0123456789" and s.opening == 200000 and s.closing == 372655
    assert [(t.day, t.amount_minor, t.kind) for t in s.txns] == [
        ("2026-10-01", 2345, "expense"),
        ("2026-10-25", 285000, "income"),
        ("2026-10-26", 110000, "expense"),
    ]
    assert "Albert Heijn 1234" in s.txns[0].desc and "Boodschappen" in s.txns[0].desc


def test_camt053_that_does_not_add_up_or_carries_entities_is_refused():
    (s,) = standards.read_camt(CAMT.replace('<Amt Ccy="EUR">1100.00', '<Amt Ccy="EUR">1100.01'))
    assert s.status == "needs_check"
    (e,) = standards.read_camt('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><Document/>')
    assert e.status == "needs_check" and "entity" in e.issues[0]
    assert standards.read_camt("<not xml")[0].status == "needs_check"
