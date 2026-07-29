*&---------------------------------------------------------------------*
*& Report ZCGX_ACTIVATE_BCSET
*& Cognixa example - activate BC Set via SCPR_ACTIVATE_BCSETS_REMOTE
*& Fixed for CALL_FUNCTION_CONFLICT_TYPE (use BCSET_IDS / SCPR_PARNT).
*&---------------------------------------------------------------------*
REPORT zcgx_activate_bcset.

PARAMETERS: p_bcset TYPE scpr_id OBLIGATORY DEFAULT 'ZCGX_FI_CGX1',
            p_sim   TYPE char1 DEFAULT ' ',
            p_rfc   TYPE rfcdest DEFAULT ' ',
            p_cust  TYPE trkorr DEFAULT ' '.

DATA: lt_bcsets    TYPE STANDARD TABLE OF scpr_parnt WITH DEFAULT KEY,
      ls_bcset     TYPE scpr_parnt,
      lv_task_cust TYPE trkorr,
      lv_task_syst TYPE trkorr,
      lv_rc        TYPE scpracst,
      lv_proto     TYPE scpr_handl.

START-OF-SELECTION.
  CLEAR ls_bcset.
  ls_bcset-bcset_id = p_bcset.
  APPEND ls_bcset TO lt_bcsets.

  lv_task_cust = p_cust.

  WRITE: / 'Cognixa BC Set activation example',
         / 'BC Set:', p_bcset,
         / 'Simulation:', p_sim,
         / 'RFC dest (blank=local):', p_rfc,
         / 'Customizing TR (optional):', p_cust.

  " Interface: TABLES BCSET_IDS TYPE SCPR_PARNT
  "            IMPORTING RC_ACTIV TYPE SCPRACST
  " Check SE37 on your release if this still dumps.
  CALL FUNCTION 'SCPR_ACTIVATE_BCSETS_REMOTE'
    EXPORTING
      simulation_on    = p_sim
      rfcdest          = p_rfc
      batch_mode       = 'N'
      task_number_cust = lv_task_cust
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

  IF sy-subrc <> 0.
    WRITE: / 'ERROR sy-subrc=', sy-subrc,
           / '1=no_authority 2=no_bcset 3=wrong_parameters',
           / '4=no_rfc_authority 5=rfc_failure 6=internal 7=batch',
           / 'Open SE37 SCPR_ACTIVATE_BCSETS_REMOTE if type dump persists.'.
    RETURN.
  ENDIF.

  WRITE: / 'Activation RC:', lv_rc,
         / 'Customizing TR:', lv_task_cust,
         / 'Workbench/System TR:', lv_task_syst,
         / 'Next: SE09 release -> STMS import QAS/PRD',
         / 'Verify: OX02 / SE16N T001 = CGX1'.
