import json,os,glob,sys,datetime
# usage: build_data.py <bundles_dir> <ios> <build> <device_id> <device_name> > data.json
#   напр.: build_data.py bundles 27.0 24A437 iPhone18,3 'iPhone 17' > data.json
os.chdir(sys.argv[1])
def load(b):
    d={}
    for f in [b+'.bundle/carrier.plist.json',b+'.bundle/overrides_V53_V54_V57.plist.json']:
        if os.path.exists(f):
            try: j=json.load(open(f))
            except Exception: continue
            for k,v in j.items():
                if isinstance(v,dict) and isinstance(d.get(k),dict): d[k]={**d[k],**v}
                else: d[k]=v
    return d
def g(o,*ks):
    for k in ks:
        if not isinstance(o,dict): return None
        o=o.get(k)
    return o
out=[]
for p in sorted(glob.glob('*.bundle'),key=str.lower):
    b=p[:-7]
    if b=='Default': continue
    d=load(b)
    ims=d.get('IMSConfig') if isinstance(d.get('IMSConfig'),dict) else {}
    ac=g(ims,'Media','AudioCodecs') or {}
    codecs=[c.get('EncodingName') for c in ac.values() if isinstance(c,dict)] if isinstance(ac,dict) else []
    apns=[a for a in (d.get('apns') or []) if isinstance(a,dict)]
    tm=lambda a:a.get('type-mask') if isinstance(a.get('type-mask'),int) else 0
    inet=[a for a in apns if tm(a)&1]; imsa=[a for a in apns if tm(a)&131072]; mmsa=[a for a in apns if tm(a)&4]
    ts=d.get('TechSettings') if isinstance(d.get('TechSettings'),dict) else {}
    ike=ts.get('IKE') if isinstance(ts.get('IKE'),dict) else {}
    ir=ts.get('iRatPolicies') if isinstance(ts.get('iRatPolicies'),dict) else {}
    e=[x for x in (d.get('APNEditabilityTypemask'),d.get('APNEditabilityTypemaskNew')) if isinstance(x,int)]
    em=0
    for x in e: em|=x
    ce=g(d,'CarrierEntitlements','SupportedEntitlements')
    mms=d.get('MMS') if isinstance(d.get('MMS'),dict) else {}
    reg=d.get('PhoneNumberRegistrationGatewayAddress'); reg=reg if isinstance(reg,list) else ([reg] if reg else [])
    vm=d.get('com.apple.voicemail.imap') if isinstance(d.get('com.apple.voicemail.imap'),dict) else {}
    xcap=g(ims,'XCAP','supported')
    out.append(dict(b=b,sims=[str(x) for x in (d.get('SupportedSIMs') or [])][:4],
      inet=(inet[0].get('apn') or '') if inet else '', inetp=inet[0].get('AllowedProtocolMask') if inet else None,
      em=em, hasEdit=bool(e), attachEdit=d.get('AllowAttachAPNEditing'),
      evs='EVS' in codecs, amrwb='AMR-WB' in codecs or any('AMR-WB' in str(c) for c in codecs),
      sw5g=d.get('Show5GSwitch'), auto5g=d.get('Enable5GAutoByDefault'), en5g=d.get('Enable5GByDefault'),
      sa=d.get('Show5GStandaloneSwitch'), saDef=d.get('Enable5GStandaloneByDefault'), vonr=d.get('SupportsVoNR'),
      ims=d.get('SupportsImsCapability') is True and bool(imsa), imsp=imsa[0].get('AllowedProtocolMask') if imsa else None,
      volteDef=g(ims,'Voice','EnableVolteByDefault'), vs=d.get('ShowVolteSwitch'),
      ra=ike.get('RemoteAddress') or '', wo=d.get('EnableWiFiCallingWithoutEntitlement', ims.get('EnableWiFiCallingWithoutEntitlement')),
      ce=ce if isinstance(ce,int) else None,
      ipsec=g(ims,'Signaling','UseIPSec'), auth=g(ims,'Signaling','DefaultAuthAlgorithm'),
      ho=ts.get('SupportCallHandover'), dpd=ike.get('DeadPeerDetectionEnabled'), lid=bool(ike.get('LocalIdentifier')),
      ih=(ir.get('PreferredTechnology') or '').lower(), ir=(ir.get('PreferredTechnologyRoaming') or ir.get('PreferredTechnologyInRoaming') or '').lower(),
      wroam=ts.get('WifiCallingAllowedInRoaming', d.get('WifiCallingAllowedInRoaming')),
      wn=d.get('OverrideOperatorWiFiName') or '',
      vvm=d.get('VisualVoicemailServiceName'), beacon=vm.get('BeaconAddress') or '',
      reg=reg[0] if reg else '', regn=len(reg),
      mmsc=mms.get('MMSC') or '', mmsproxy=mms.get('Proxy') or '', mmsapn=(mmsa[0].get('apn') or '') if mmsa else '',
      lte=d.get('DataIndicatorOverrideForLTE') or d.get('DataIndicatorOverride') or '',
      xcap=xcap, vmpilot=d.get('VoicemailPilotNumber') or ''))
meta=dict(ios=sys.argv[2],build=sys.argv[3],device=sys.argv[4],deviceName=sys.argv[5] if len(sys.argv)>5 else sys.argv[4],count=len(out),generated=datetime.date.today().isoformat())
json.dump(dict(meta=meta,bundles=out),sys.stdout,ensure_ascii=False,separators=(',',':'))
