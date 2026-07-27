*&---------------------------------------------------------------------*
*& Report ZCGX_DEPLOY_ENT_CFG_TEST
*& Local test harness for ZCGX_DEPLOY_ENTERPRISE_CFG (RFC API)
*& Paste into SE38, Activate, F8.
*&---------------------------------------------------------------------*
REPORT zcgx_deploy_ent_cfg_test.

PARAMETERS: p_pb    TYPE char40 DEFAULT 'CFG-BOT/BCSET/FI/ORG',
            p_bc1   TYPE scpr_id OBLIGATORY DEFAULT 'ZCGX_FI_CGX1',
            p_bc2   TYPE scpr_id DEFAULT ' ',
            p_bc3   TYPE scpr_id DEFAULT ' ',
            p_sim   TYPE char1 DEFAULT ' ',
            p_cust  TYPE trkorr DEFAULT ' '.

DATA: lt_bcsets  TYPE STANDARD TABLE OF scpr_parnt WITH DEFAULT KEY,
      ls_bcset   TYPE scpr_parnt,
      lt_msg     TYPE STANDARD TABLE OF bapiret2 WITH DEFAULT KEY,
      ls_msg     TYPE bapiret2,
      lv_rc      TYPE scpracst,
      lv_tcust   TYPE trkorr,
      lv_tsyst   TYPE trkorr,
      lv_proto   TYPE scpr_handl,
      lv_subrc   TYPE sysubrc,
      lv_message TYPE char255.

START-OF-SELECTION.
  CLEAR ls_bcset.
  ls_bcset-bcset_id = p_bc1.
  APPEND ls_bcset TO lt_bcsets.

  IF p_bc2 IS NOT INITIAL.
    CLEAR ls_bcset.
    ls_bcset-bcset_id = p_bc2.
    APPEND ls_bcset TO lt_bcsets.
  ENDIF.

  IF p_bc3 IS NOT INITIAL.
    CLEAR ls_bcset.
    ls_bcset-bcset_id = p_bc3.
    APPEND ls_bcset TO lt_bcsets.
  ENDIF.

  WRITE: / 'Cognixa enterprise/config deploy TEST',
         / 'Playbook:', p_pb,
         / 'Simulation:', p_sim.

  CALL FUNCTION 'ZCGX_DEPLOY_ENTERPRISE_CFG'
    EXPORTING
      iv_playbook      = p_pb
      iv_simulation    = p_sim
      iv_task_cust     = p_cust
    IMPORTING
      ev_rc_activ      = lv_rc
      ev_task_cust     = lv_tcust
      ev_task_syst     = lv_tsyst
      ev_proto         = lv_proto
      ev_subrc         = lv_subrc
      ev_message       = lv_message
    TABLES
      it_bcsets        = lt_bcsets
      et_messages      = lt_msg
    EXCEPTIONS
      no_bcset         = 1
      no_authority     = 2
      activation_failed = 3
      wrong_input      = 4
      OTHERS           = 5.

  WRITE: / 'FM sy-subrc:', sy-subrc,
         / 'EV_SUBRC:', lv_subrc,
         / 'EV_RC_ACTIV:', lv_rc,
         / 'EV_TASK_CUST:', lv_tcust,
         / 'EV_TASK_SYST:', lv_tsyst,
         / 'EV_MESSAGE:', lv_message.

  LOOP AT lt_msg INTO ls_msg.
    WRITE: / ls_msg-type, ls_msg-message.
  ENDLOOP.

  WRITE: / 'Verify OX02 / SE16N for objects contained in the BC Sets.'.
  WRITE: / 'Next: SE09 release customizing TR -> STMS QAS/PRD.'.
