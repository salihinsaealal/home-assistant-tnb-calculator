#!/usr/bin/env python3
"""Debug calculation to understand the ToU vs Non-ToU difference."""

# From screenshot
import_peak = 0.789
import_offpeak = 0.0
export_total = 0.0

print("="*60)
print("INPUT DATA (from screenshot)")
print("="*60)
print(f"Import Peak Energy: {import_peak} kWh")
print(f"Import Off-Peak Energy: {import_offpeak} kWh")
print(f"Export Total: {export_total} kWh")

print("\n" + "="*60)
print("ToU CALCULATION (your template)")
print("="*60)

# Derived quantities
import_total = import_peak + import_offpeak
export_peak = min(import_peak, export_total)
export_offpeak = export_total - export_peak

print(f"\nDerived:")
print(f"  import_total = {import_total} kWh")
print(f"  export_peak = {export_peak} kWh")
print(f"  export_offpeak = {export_offpeak} kWh")

# Effective rates
if import_total < 1500:
    gen_peak_eff = 0.2852
    gen_off_eff = 0.2443
else:
    gen_peak_eff = 0.3852
    gen_off_eff = 0.3443

cap_rate = 0.0455
netw_rate = 0.1285

# AFA & Retailing
afa = 0.0 if import_total < 600 else import_total * 0.0145
retailing = 10.0 if import_total > 600 else 0.0

# ICT lookup
tiers = [
    (1, -0.25),(201,-0.245),(251,-0.225),(301,-0.21),(351,-0.17),
    (401,-0.145),(451,-0.12),(501,-0.105),(551,-0.09),(601,-0.075),
    (651,-0.055),(701,-0.045),(751,-0.04),(801,-0.025),(851,-0.01),(901,-0.005)
]
ict_rate = tiers[0][1]
for limit, rate in tiers:
    if import_total >= limit:
        ict_rate = rate

ict_adj = import_total * ict_rate

# Import charges
e10_peak = import_peak * gen_peak_eff
e11_off = import_offpeak * gen_off_eff
e13_cap = import_total * cap_rate
e14_netw = import_total * netw_rate
e12_afa = afa
e15_retail = retailing
e17_ict = ict_adj
e18_import_charge = e10_peak + e11_off + e12_afa + e13_cap + e14_netw + e15_retail + e17_ict

# Service Tax & KWTBB
e19_st = (e18_import_charge * 0.08) if import_total > 600 else 0.0
e20_kw = (e18_import_charge * 0.016) if import_total > 300 else 0.0

# NEM rebate
nem_peak_rate = 0.2852
nem_off_rate = 0.2443
e23_nem_peak = -export_peak * nem_peak_rate
e24_nem_off = -export_offpeak * nem_off_rate
e25_nem_cap = -export_total * cap_rate
e26_nem_netw = -export_total * netw_rate
nem_rebate_sum = e23_nem_peak + e24_nem_off + e25_nem_cap + e26_nem_netw

# Insentif
e28_insentif = -export_total * ict_rate

# Final
e30_final = e18_import_charge + e19_st + e20_kw + nem_rebate_sum + e28_insentif

print(f"\nRates:")
print(f"  gen_peak_eff = {gen_peak_eff} RM/kWh")
print(f"  gen_off_eff = {gen_off_eff} RM/kWh")
print(f"  ict_rate = {ict_rate} RM/kWh")

print(f"\nImport Charges:")
print(f"  E10 Peak Charge = {e10_peak:.6f} RM")
print(f"  E11 Off-Peak Charge = {e11_off:.6f} RM")
print(f"  E12 AFA = {e12_afa:.6f} RM")
print(f"  E13 Capacity = {e13_cap:.6f} RM")
print(f"  E14 Network = {e14_netw:.6f} RM")
print(f"  E15 Retailing = {e15_retail:.6f} RM")
print(f"  E17 ICT = {e17_ict:.6f} RM")
print(f"  E18 TOTAL IMPORT = {e18_import_charge:.6f} RM")

print(f"\nTaxes:")
print(f"  E19 Service Tax = {e19_st:.6f} RM")
print(f"  E20 KWTBB = {e20_kw:.6f} RM")

print(f"\nNEM Rebates:")
print(f"  E23 NEM Peak = {e23_nem_peak:.6f} RM")
print(f"  E24 NEM Off-Peak = {e24_nem_off:.6f} RM")
print(f"  E25 NEM Capacity = {e25_nem_cap:.6f} RM")
print(f"  E26 NEM Network = {e26_nem_netw:.6f} RM")
print(f"  NEM Total = {nem_rebate_sum:.6f} RM")

print(f"\nInsentif:")
print(f"  E28 Insentif = {e28_insentif:.6f} RM")

print(f"\nFINAL ToU COST: {e30_final:.2f} RM")

print("\n" + "="*60)
print("NON-ToU CALCULATION (your template)")
print("="*60)

import_kwh = import_total
export_kwh = export_total

# ICT Rate
if import_kwh <= 200:
    ict_rate_nontou = -0.25
elif import_kwh <= 250:
    ict_rate_nontou = -0.245
elif import_kwh <= 300:
    ict_rate_nontou = -0.225
elif import_kwh <= 350:
    ict_rate_nontou = -0.21
elif import_kwh <= 400:
    ict_rate_nontou = -0.17
elif import_kwh <= 450:
    ict_rate_nontou = -0.145
elif import_kwh <= 500:
    ict_rate_nontou = -0.12
elif import_kwh <= 550:
    ict_rate_nontou = -0.105
elif import_kwh <= 600:
    ict_rate_nontou = -0.09
elif import_kwh <= 650:
    ict_rate_nontou = -0.075
elif import_kwh <= 700:
    ict_rate_nontou = -0.055
elif import_kwh <= 750:
    ict_rate_nontou = -0.045
elif import_kwh <= 800:
    ict_rate_nontou = -0.04
elif import_kwh <= 850:
    ict_rate_nontou = -0.025
elif import_kwh <= 900:
    ict_rate_nontou = -0.01
elif import_kwh <= 1000:
    ict_rate_nontou = -0.005
else:
    ict_rate_nontou = 0

# Tier 1
import_tier1 = min(import_kwh, 600)
import_caj_tier1 = import_tier1 * 0.2703
import_capacity_tier1 = import_tier1 * 0.0455
import_network_tier1 = import_tier1 * 0.1285
import_runcit_tier1 = 0
import_ict_tier1 = import_tier1 * ict_rate_nontou
import_kwtbb_tier1 = (import_caj_tier1 + import_capacity_tier1 + import_network_tier1 + import_ict_tier1) * 0.016

# Tier 2
import_tier2 = max(import_kwh - 600, 0)
import_caj_tier2 = import_tier2 * 0.2703
import_capacity_tier2 = import_tier2 * 0.0455
import_network_tier2 = import_tier2 * 0.1285
import_runcit_tier2 = 10 if import_tier2 > 0 else 0
import_ict_tier2 = import_tier2 * ict_rate_nontou
import_kwtbb_tier2 = (import_caj_tier2 + import_capacity_tier2 + import_network_tier2 + import_ict_tier2) * 0.016
import_service_tax = (import_caj_tier2 + import_capacity_tier2 + import_network_tier2 + import_runcit_tier2 + import_ict_tier2) * 0.08

# Totals
total_import_caj = import_caj_tier1 + import_caj_tier2
total_import_capacity = import_capacity_tier1 + import_capacity_tier2
total_import_network = import_network_tier1 + import_network_tier2
total_import_runcit = import_runcit_tier1 + import_runcit_tier2
total_import_ict = import_kwh * ict_rate_nontou
total_import_kwtbb = (import_kwtbb_tier1 + import_kwtbb_tier2) if import_kwh > 300 else 0
total_import_service_tax = import_service_tax

total_import = total_import_caj + total_import_capacity + total_import_network + total_import_runcit + total_import_ict + total_import_kwtbb + total_import_service_tax

# Export
export_caj = export_kwh * -0.2703
export_capacity = export_kwh * -0.0455
export_network = export_kwh * -0.1285
export_ict = export_kwh * -ict_rate_nontou

total_export = export_caj + export_capacity + export_network + export_ict

subtotal = total_import + total_export

print(f"Import: {import_kwh} kWh")
print(f"Export: {export_kwh} kWh")
print(f"ICT Rate: {ict_rate_nontou} RM/kWh")
print(f"\nCharges:")
print(f"  Caj/Energy: {total_import_caj:.6f} RM")
print(f"  Capacity: {total_import_capacity:.6f} RM")
print(f"  Network: {total_import_network:.6f} RM")
print(f"  Retailing: {total_import_runcit:.6f} RM")
print(f"  ICT: {total_import_ict:.6f} RM")
print(f"  KWTBB: {total_import_kwtbb:.6f} RM")
print(f"  Service Tax: {total_import_service_tax:.6f} RM")
print(f"  Total Import: {total_import:.6f} RM")
print(f"  Total Export: {total_export:.6f} RM")

print(f"\nFINAL NON-ToU COST: {subtotal:.2f} RM")

print("\n" + "="*60)
print("COMPARISON")
print("="*60)
print(f"Non-ToU Cost: {subtotal:.2f} RM")
print(f"ToU Cost: {e30_final:.2f} RM")
print(f"Difference: {e30_final - subtotal:.2f} RM")
if e30_final > subtotal:
    print("✓ ToU is MORE expensive (as expected during peak)")
else:
    print("✗ ToU is LESS expensive (WRONG - should be higher during peak!)")
