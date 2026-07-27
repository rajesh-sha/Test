*&---------------------------------------------------------------------*
*& Function Module  ZCGX_DEPLOY_ENTERPRISE_CFG
*& Cognixa — remote-enabled deploy of enterprise/config BC Sets
*&
*& INSTALL:
*&  1. SE80: create function group ZCGX_CFG
*&  2. Create FM ZCGX_DEPLOY_ENTERPRISE_CFG as Remote-Enabled
*&  3. Create parameters as documented in IMPORT.md / below
*&  4. Paste this source into the FM, Activate
*&
*& DESIGN:
*&  Pass BC Set IDs (packaged enterprise structure), not raw table rows.
*&  Uses SCPR_ACTIVATE_BCSETS_REMOTE (SAP standard activation path).
*&---------------------------------------------------------------------*
FUNCTION zcgx_deploy_enterprise_cfg.
*"----------------------------------------------------------------------
*"*"Local Interface:
*"  IMPORTING
*"     VALUE(IV_PLAYBOOK) TYPE CHAR40 OPTIONAL
*"     VALUE(IV_SIMULATION) TYPE CHAR1 DEFAULT SPACE
*"     VALUE(IV_RFCDEST) TYPE RFCDES-RFCDEST DEFAULT SPACE
*"     VALUE(IV_TASK_CUST) TYPE TRKORR DEFAULT SPACE
*"     VALUE(IV_TRANSPORT_OFF) TYPE CHAR1 DEFAULT 'N'
*"  EXPORTING
*"     VALUE(EV_RC_ACTIV) TYPE SCPRACST
*"     VALUE(EV_TASK_CUST) TYPE TRKORR
*"     VALUE(EV_TASK_SYST) TYPE TRKORR
*"     VALUE(EV_PROTO) TYPE SCPR_HANDL
*"     VALUE(EV_SUBRC) TYPE SYSUBRC
*"     VALUE(EV_MESSAGE) TYPE CHAR255
*"  TABLES
*"      IT_BCSETS STRUCTURE  SCPR_PARNT
*"      ET_MESSAGES STRUCTURE  BAPIRET2 OPTIONAL
*"  EXCEPTIONS
*"      NO_BCSET
*"      NO_AUTHORITY
*"      ACTIVATION_FAILED
*"      WRONG_INPUT
*"----------------------------------------------------------------------

  DATA: lt_bcsets    TYPE STANDARD TABLE OF scpr_parnt WITH DEFAULT KEY,
        ls_bcset     TYPE scpr_parnt,
        ls_msg       TYPE bapiret2,
        lv_task_cust TYPE trkorr,
        lv_task_syst TYPE trkorr,
        lv_rc        TYPE scpracst,
        lv_proto     TYPE scpr_handl,
        lv_count     TYPE i.

  CLEAR: ev_rc_activ, ev_task_cust, ev_task_syst, ev_proto, ev_subrc, ev_message.
  IF et_messages IS SUPPLIED.
    REFRESH et_messages.
  ENDIF.

  " --- validate input ---
  lv_count = lines( it_bcsets ).
  IF lv_count = 0.
    ev_subrc = 4.
    ev_message = 'WRONG_INPUT: IT_BCSETS is empty — pass BC Set IDs (enterprise packages)'.
    ls_msg-type = 'E'.
    ls_msg-id = '00'.
    ls_msg-number = '001'.
    ls_msg-message = ev_message.
    IF et_messages IS SUPPLIED.
      APPEND ls_msg TO et_messages.
    ENDIF.
    RAISE wrong_input.
  ENDIF.

  LOOP AT it_bcsets INTO ls_bcset.
    IF ls_bcset-bcset_id IS INITIAL.
      ev_subrc = 4.
      ev_message = 'WRONG_INPUT: BCSET_ID initial in IT_BCSETS'.
      RAISE wrong_input.
    ENDIF.
    APPEND ls_bcset TO lt_bcsets.
  ENDLOOP.

  lv_task_cust = iv_task_cust.

  ls_msg-type = 'I'.
  ls_msg-message = |Cognixa deploy playbook={ iv_playbook } bcsets={ lv_count } sim={ iv_simulation }|.
  IF et_messages IS SUPPLIED.
    APPEND ls_msg TO et_messages.
  ENDIF.

  " --- SAP standard activation (enterprise structure content = BC Sets) ---
  CALL FUNCTION 'SCPR_ACTIVATE_BCSETS_REMOTE'
    EXPORTING
      simulation_on    = iv_simulation
      rfcdest          = iv_rfcdest
      batch_mode       = 'N'
      task_number_cust = lv_task_cust
      transport_off    = iv_transport_off
    IMPORTING
      proto_handle     = lv_proto
      rc_activ         = lv_rc
      task_syst_exp    = lv_task_syst
      task_cust_exp    = lv_task_cust
    TABLES
      bcset_ids        = lt_bcsets
    EXCEPTIONS
      no_authority     = 1
      no_bcset         = 2
      wrong_parameters = 3
      no_rfc_authority = 4
      rfc_failure      = 5
      internal_error   = 6
      batchjob_error   = 7
      OTHERS           = 8.

  ev_subrc     = sy-subrc.
  ev_rc_activ  = lv_rc.
  ev_task_cust = lv_task_cust.
  ev_task_syst = lv_task_syst.
  ev_proto     = lv_proto.

  CASE sy-subrc.
    WHEN 0.
      ev_message = |OK RC={ lv_rc } CUST_TR={ lv_task_cust } PROTO={ lv_proto }|.
      ls_msg-type = 'S'.
      ls_msg-message = ev_message.
      IF et_messages IS SUPPLIED.
        APPEND ls_msg TO et_messages.
      ENDIF.
    WHEN 1.
      ev_message = 'NO_AUTHORITY: missing BC Set / customizing authorization'.
      IF et_messages IS SUPPLIED.
        ls_msg-type = 'E'. ls_msg-message = ev_message. APPEND ls_msg TO et_messages.
      ENDIF.
      RAISE no_authority.
    WHEN 2.
      ev_message = 'NO_BCSET: one or more BC Sets do not exist — create in SCPR3 first'.
      IF et_messages IS SUPPLIED.
        ls_msg-type = 'E'. ls_msg-message = ev_message. APPEND ls_msg TO et_messages.
      ENDIF.
      RAISE no_bcset.
    WHEN OTHERS.
      ev_message = |ACTIVATION_FAILED: sy-subrc={ sy-subrc } — check SE37 SCPR_ACTIVATE_BCSETS_REMOTE|.
      IF et_messages IS SUPPLIED.
        ls_msg-type = 'E'. ls_msg-message = ev_message. APPEND ls_msg TO et_messages.
      ENDIF.
      RAISE activation_failed.
  ENDCASE.

ENDFUNCTION.
