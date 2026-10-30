"""Typed relation binding for experimental R6.1-D selectors."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any
from viirr_retrieval.ontology_query_guide import normalize_vietnamese

class Verdict(str,Enum): MATCHED='MATCHED'; PARTIAL='PARTIALLY_MATCHED'; UNKNOWN='UNKNOWN'; CONFLICTING='CONFLICTING'; NOT_MATCHED='NOT_MATCHED'
@dataclass(frozen=True)
class QuestionRequirement:
 entity:str|None; parameter:str|None; expected_unit:str|None=None; temporal_scope:str|None=None; confidence:float=0.0; question_type:str='single_fact'
@dataclass(frozen=True)
class Binding:
 verdict:Verdict; entity_ok:bool; parameter_ok:bool; unit_ok:bool|None; temporal_ok:bool|None; provenance_ok:bool; reason:str
def _eq(a:str|None,b:str|None)->bool:
 return bool(a and b and (normalize_vietnamese(a) in normalize_vietnamese(b) or normalize_vietnamese(b) in normalize_vietnamese(a)))
def bind(requirement:QuestionRequirement,evidence:dict[str,Any])->Binding:
 entity_ok=_eq(requirement.entity,str(evidence.get('entity') or ''))
 parameter_ok=_eq(requirement.parameter,str(evidence.get('parameter') or ''))
 unit_ok=None if not requirement.expected_unit else _eq(requirement.expected_unit,str(evidence.get('unit') or ''))
 temporal_ok=None if not requirement.temporal_scope else _eq(requirement.temporal_scope,str(evidence.get('condition') or evidence.get('header_context') or ''))
 provenance_ok=bool(evidence.get('evidence_id') and evidence.get('page_id') and evidence.get('doc_id'))
 if entity_ok and parameter_ok and unit_ok is not False and temporal_ok is not False and provenance_ok:return Binding(Verdict.MATCHED,entity_ok,parameter_ok,unit_ok,temporal_ok,provenance_ok,'typed fields agree')
 if entity_ok and not parameter_ok:return Binding(Verdict.CONFLICTING,entity_ok,parameter_ok,unit_ok,temporal_ok,provenance_ok,'entity matches but parameter differs')
 if parameter_ok and not entity_ok:return Binding(Verdict.CONFLICTING,entity_ok,parameter_ok,unit_ok,temporal_ok,provenance_ok,'parameter matches but entity differs')
 if evidence.get('unit_type')=='TABLE_REGION':return Binding(Verdict.UNKNOWN,entity_ok,parameter_ok,unit_ok,temporal_ok,provenance_ok,'whole table lacks cell binding')
 return Binding(Verdict.PARTIAL if entity_ok or parameter_ok else Verdict.NOT_MATCHED,entity_ok,parameter_ok,unit_ok,temporal_ok,provenance_ok,'incomplete typed relation')
