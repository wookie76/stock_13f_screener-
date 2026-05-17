from stock_13f_screener.parse_13f import parse_information_table_xml


def test_parse_information_table_xml() -> None:
    xml = """
    <informationTable>
      <infoTable>
        <nameOfIssuer>APPLE INC</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>037833100</cusip>
        <value>1000</value>
        <shrsOrPrnAmt>
          <sshPrnamt>10</sshPrnamt>
          <sshPrnamtType>SH</sshPrnamtType>
        </shrsOrPrnAmt>
        <investmentDiscretion>SOLE</investmentDiscretion>
        <votingAuthority>
          <Sole>10</Sole>
          <Shared>0</Shared>
          <None>0</None>
        </votingAuthority>
      </infoTable>
    </informationTable>
    """
    metadata = {
        "institution_cik": "0001364742",
        "institution_name": "BlackRock",
        "manager_type": "passive_giant",
        "signal_weight": 0.4,
    }
    rows = parse_information_table_xml(xml, metadata)
    assert len(rows) == 1
    assert rows[0]["cusip"] == "037833100"
    assert rows[0]["issuer_name"] == "APPLE INC"
    assert rows[0]["shares"] == 10.0 or rows[0]["shares"] == "10"
