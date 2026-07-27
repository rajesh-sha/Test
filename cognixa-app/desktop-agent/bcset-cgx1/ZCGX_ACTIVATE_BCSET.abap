*&---------------------------------------------------------------------*
*& Report ZCGX_ACTIVATE_BCSET
*& Cognixa example - activate BC Set via SCPR_ACTIVATE_BCSETS_REMOTE
*& Preferred On-Prem automation vs SAP GUI scripting.
*&---------------------------------------------------------------------*
REPORT zcgx_activate_bcset.

PARAMETERS: p_bcset TYPE scpr_id OBLIGATORY DEFAULT 'ZCGX_FI_CGX1',
            p_sim   TYPE char1 DEFAULT ' ',
            p_rfc   TYPE rfcdest DEFAULT ' '.

TYPES: BEGIN OF ty_bcset,
         bcset TYPE scpr_id,
       END OF ty_bcset.

DATA: lt_bcsets TYPE STANDARD TABLE OF ty_bcset,
      ls_bcset  TYPE ty_bcset,
      lv_task_cust TYPE trkorr,
      lv_task_syst TYPE trkorr,
      lv_rc        TYPE i,
      lv_proto     TYPE scpr_handl.

START-OF-SELECTION.
  ls_bcset-bcset = p_bcset.
  APPEND ls_bcset TO lt_bcsets.

  WRITE: / 'Cognixa BC Set activation example',
         / 'BC Set:', p_bcset,
         / 'Simulation:', p_sim,
         / 'RFC dest (blank=local):', p_rfc.

  " Remote-enabled FM in function group SCPR.
  " Exact TABLES/IMPORT signature can vary by SAP_BASIS SP - adjust in SE37 if needed.
  CALL FUNCTION 'SCPR_ACTIVATE_BCSETS_REMOTE'
    EXPORTING
      simulation_on = p_sim
      rfcdest       = p_rfc
      batch_mode    = 'N'
    IMPORTING
      proto_handle  = lv_proto
      rc_activ      = lv_rc
      task_syst_exp = lv_task_syst
      task_cust_exp = lv_task_cust
    TABLES
      bcset_list    = lt_bcsets
    EXCEPTIONS
      no_authority      = 1
      no_bcset          = 2
      wrong_parameters  = 3
      no_rfc_authority  = 4
      rfc_failure       = 5
      internal_error    = 6
      batchjob_error    = 7
      OTHERS            = 8.

  IF sy-subrc <> 0.
    WRITE: / 'ERROR sy-subrc=', sy-subrc,
           / 'Check SE37 signature for SCPR_ACTIVATE_BCSETS_REMOTE on this release,',
           / 'BC Set exists in SCPR20, and user has S_BCSETS / customizing auth.'.
    RETURN.
  ENDIF.

  WRITE: / 'Activation RC:', lv_rc,
         / 'Customizing TR:', lv_task_cust,
         / 'Workbench/System TR:', lv_task_syst,
         / 'Next: SE09 release -> STMS import QAS/PRD',
         / 'Verify: OX02 / SE16N T001 = CGX1'.
