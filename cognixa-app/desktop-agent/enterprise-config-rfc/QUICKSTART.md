## Quick start — import RFC deploy API into client

1. Open folder `enterprise-config-rfc/`
2. Follow `IMPORT.md`
3. Paste FM from `abap/ZCGX_DEPLOY_ENTERPRISE_CFG.abap`
4. Paste test report from `abap/ZCGX_DEPLOY_ENT_CFG_TEST.abap`
5. Create BC Sets (see `example-enterprise-bcsets.json`)
6. Test locally, then call FM via SM59 RFC with technical user

This is the Cognixa-supported way to deploy enterprise structure **without interactive SAP logon**.
