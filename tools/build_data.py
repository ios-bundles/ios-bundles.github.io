#!/usr/bin/env python3
"""Сборка data.json из распакованных пакетов оператора iOS.

usage: build_data.py <bundles_dir> <ios> <build> <device_id> <device_name> [override_suffix] [country_bundles_dir] > data.json
  напр.: build_data.py bundles 27.0 24A437 iPhone18,3 'iPhone 17' V53_V54_V57 CountryBundles > data.json

Как собираются настройки пакета:
  1. carrier.plist, поверх него глубоко — overrides_<suffix>.plist (override платы);
  2. поверх — страновой пакет (CountryBundles/<Страна>.bundle, тоже carrier.plist +
     override) той страны, чей MCC стоит в SupportedSIMs пакета (257 → Belarus,
     250 → Russia …): его значения перекрывают значения пакета оператора;
  3. ключи, которых нет нигде, — из Default.bundle, затем значение по умолчанию
     CommCenter (CODE_DEFAULTS).
"""
import datetime, glob, json, os, plistlib, sys

bdir, ios, build, dev_id = sys.argv[1:5]
dev_name = sys.argv[5] if len(sys.argv) > 5 else dev_id
suffix = sys.argv[6] if len(sys.argv) > 6 else 'V53_V54_V57'
cdir = sys.argv[7] if len(sys.argv) > 7 else None

# Значения по умолчанию, зашитые в CommCenter (iOS 27.0), для ключей,
# которых нет ни в пакете, ни в Default.bundle.
CODE_DEFAULTS = {
    'Show5GSwitch': True,          # проверка «5G switch is supported» читает ключ с default = true
}
# служебные ключи странового пакета, которые не относятся к настройкам
COUNTRY_META = {'CountryName', 'ISOAlpha2CountryCode', 'SupportedCountryIds'}


def read_plist(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'rb') as f:
            v = plistlib.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:
        try:
            with open(path + '.json') as f:
                return json.load(f)
        except Exception:
            return {}


def deep_merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def bundle_dict(path):
    return deep_merge(read_plist(os.path.join(path, 'carrier.plist')),
                      read_plist(os.path.join(path, f'overrides_{suffix}.plist')))


def g(o, *ks):
    for k in ks:
        if not isinstance(o, dict):
            return None
        o = o.get(k)
    return o


def plain(v):
    """bytes и прочее несериализуемое → None."""
    return v if isinstance(v, (str, int, float, bool)) or v is None else None


DEFAULT = bundle_dict(os.path.join(bdir, 'Default.bundle'))

# MCC → (название страны, настройки странового пакета)
COUNTRY_BY_MCC = {}
if cdir:
    for p in glob.glob(os.path.join(cdir, '*.bundle')):
        cd = bundle_dict(p)
        name = str(cd.get('CountryName') or os.path.basename(p)[:-7])
        settings = {k: v for k, v in cd.items() if k not in COUNTRY_META}
        for mcc in (cd.get('SupportedCountryIds') or []):
            mcc = str(mcc)
            if mcc.isdigit():
                COUNTRY_BY_MCC[mcc] = (name, settings)


def inherit(d, key):
    """(значение, источник): 'bundle' | 'default' (Default.bundle) | 'code' (CommCenter) | None."""
    if key in d:
        return plain(d[key]), 'bundle'
    if key in DEFAULT:
        return plain(DEFAULT[key]), 'default'
    if key in CODE_DEFAULTS:
        return CODE_DEFAULTS[key], 'code'
    return None, None


def extract(b, d):
    ims = d.get('IMSConfig') if isinstance(d.get('IMSConfig'), dict) else {}
    ac = g(ims, 'Media', 'AudioCodecs') or {}
    codecs = [c.get('EncodingName') for c in ac.values() if isinstance(c, dict)] if isinstance(ac, dict) else []
    apns = [a for a in (d.get('apns') or []) if isinstance(a, dict)]
    tm = lambda a: a.get('type-mask') if isinstance(a.get('type-mask'), int) else 0
    inet = [a for a in apns if tm(a) & 1]
    imsa = [a for a in apns if tm(a) & 131072]
    mmsa = [a for a in apns if tm(a) & 4]
    ts = d.get('TechSettings') if isinstance(d.get('TechSettings'), dict) else {}
    ike = ts.get('IKE') if isinstance(ts.get('IKE'), dict) else {}
    ir = ts.get('iRatPolicies') if isinstance(ts.get('iRatPolicies'), dict) else {}
    e = [x for x in (d.get('APNEditabilityTypemask'), d.get('APNEditabilityTypemaskNew')) if isinstance(x, int)]
    em = 0
    for x in e:
        em |= x
    ce = g(d, 'CarrierEntitlements', 'SupportedEntitlements')
    mms = d.get('MMS') if isinstance(d.get('MMS'), dict) else {}
    reg = d.get('PhoneNumberRegistrationGatewayAddress')
    reg = [str(x) for x in reg] if isinstance(reg, list) else ([str(reg)] if reg else [])
    vm = d.get('com.apple.voicemail.imap') if isinstance(d.get('com.apple.voicemail.imap'), dict) else {}
    sw5g, sw5gSrc = inherit(d, 'Show5GSwitch')
    vs, vsSrc = inherit(d, 'ShowVolteSwitch')
    lte = plain(d.get('DataIndicatorOverrideForLTE') or d.get('DataIndicatorOverride'))
    lteSrc = 'bundle' if lte else None
    if not lte:
        lte, lteSrc = inherit(d, 'DataIndicatorOverrideForLTE')
    return dict(
        b=b, sims=[str(x) for x in (d.get('SupportedSIMs') or [])][:4],
        inet=str((inet[0].get('apn') or '')) if inet else '', inetp=inet[0].get('AllowedProtocolMask') if inet else None,
        em=em, hasEdit=bool(e),
        evs='EVS' in codecs,
        sw5g=sw5g, sw5gSrc=sw5gSrc,
        auto5g=plain(d.get('Enable5GAutoByDefault')), en5g=plain(d.get('Enable5GByDefault')),
        sa=plain(d.get('Show5GStandaloneSwitch')), saDef=plain(d.get('Enable5GStandaloneByDefault')), vonr=plain(d.get('SupportsVoNR')),
        ims=d.get('SupportsImsCapability') is True and bool(imsa), imsp=imsa[0].get('AllowedProtocolMask') if imsa else None,
        volteDef=plain(g(ims, 'Voice', 'EnableVolteByDefault')), vs=vs, vsSrc=vsSrc,
        ra=str(ike.get('RemoteAddress') or ''),
        wo=plain(d.get('EnableWiFiCallingWithoutEntitlement', ims.get('EnableWiFiCallingWithoutEntitlement'))),
        ce=ce if isinstance(ce, int) else None,
        ipsec=plain(g(ims, 'Signaling', 'UseIPSec')), auth=plain(g(ims, 'Signaling', 'DefaultAuthAlgorithm')),
        ho=plain(ts.get('SupportCallHandover')), dpd=plain(ike.get('DeadPeerDetectionEnabled')), lid=bool(ike.get('LocalIdentifier')),
        ih=str(ir.get('PreferredTechnology') or '').lower(),
        ir=str(ir.get('PreferredTechnologyRoaming') or ir.get('PreferredTechnologyInRoaming') or '').lower(),
        wroam=plain(ts.get('WifiCallingAllowedInRoaming', d.get('WifiCallingAllowedInRoaming'))),
        wn=str(d.get('OverrideOperatorWiFiName') or ''),
        vvm=plain(d.get('VisualVoicemailServiceName')), beacon=str(vm.get('BeaconAddress') or ''),
        reg=reg[0] if reg else '', regn=len(reg),
        mmsc=str(mms.get('MMSC') or ''), mmsapn=str((mmsa[0].get('apn') or '')) if mmsa else '',
        lte=lte or '', lteSrc=lteSrc,
        xcap=plain(g(ims, 'XCAP', 'supported')), vmpilot=str(d.get('VoicemailPilotNumber') or ''),
    )


out = []
for p in sorted(glob.glob(os.path.join(bdir, '*.bundle')), key=str.lower):
    b = os.path.basename(p)[:-7]
    if b == 'Default':
        continue
    d = bundle_dict(p)
    rec = extract(b, d)
    sims = [str(x) for x in (d.get('SupportedSIMs') or [])]
    country = COUNTRY_BY_MCC.get(sims[0][:3]) if sims else None
    if country:
        name, settings = country
        rec_c = extract(b, deep_merge(d, settings))
        changed = [k for k in rec_c if k not in ('b', 'sims') and not k.endswith('Src') and rec_c[k] != rec[k]]
        for k in ('sw5g', 'vs', 'lte'):
            if k in changed:
                rec_c[k + 'Src'] = 'country'
        rec = rec_c
        rec['country'] = name
        rec['cf'] = changed          # поля, перекрытые страновым пакетом
    out.append(rec)

meta = dict(ios=ios, build=build, device=dev_id, deviceName=dev_name, overrides=suffix,
            countryBundles=bool(cdir), count=len(out), generated=datetime.date.today().isoformat())
json.dump(dict(meta=meta, bundles=out), sys.stdout, ensure_ascii=False, separators=(',', ':'))
