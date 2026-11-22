from opentrons import protocol_api

metadata = {"protocolName": "Flex serial dilution (test fixture)", "author": "OpentronsAgent tests"}
requirements = {"robotType": "Flex", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware("opentrons_flex_96_tiprack_200ul", "D1")
    plate = protocol.load_labware("corning_96_wellplate_360ul_flat", "D2")
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "D3")
    protocol.load_trash_bin("A3")
    pipette = protocol.load_instrument("flex_1channel_1000", "left", tip_racks=[tips])
    pipette.transfer(100, reservoir["A1"], plate.rows()[0][1:6])
    pipette.transfer(100, plate.rows()[0][:5], plate.rows()[0][1:6], mix_after=(3, 50))
