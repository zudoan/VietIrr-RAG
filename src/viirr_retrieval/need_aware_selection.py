"""Opt-in R6.1-C structure-preserving evidence-set selection.

No gold annotations or QA identifiers are consulted.  The selector operates on
authentic regions plus cells emitted by the existing table parser.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any
from viirr_retrieval.ontology_query_guide import normalize_vietnamese
from viirr_retrieval.relation_binding import QuestionRequirement, Verdict, bind

@dataclass(frozen=True)
class InformationNeed:
    entity: str | None
    parameter: str | None
    kind: str

def extract_requirements(question: str, table_facts: list[Any]) -> list[InformationNeed]:
    """Conservative, source-free extraction: only names occurring in the query."""
    q=normalize_vietnamese(question); parameter=None
    for cue in ('dung tich','muc nuoc','luu luong','cao trinh','dien tich','luong mua'):
        if cue in q: parameter=cue; break
    entities=[]
    for f in table_facts:
        e=normalize_vietnamese(getattr(f,'entity',''))
        if e and e in q and e not in entities: entities.append(e)
    kind='multi_value' if len(entities)>1 else ('table_lookup' if parameter else 'single_fact')
    return [InformationNeed(e,parameter,kind) for e in entities] or [InformationNeed(None,parameter,kind)]

def _text(row: dict[str,Any])->str: return normalize_vietnamese(str(row.get('text') or row.get('raw_text') or ''))
def _matches(row: dict[str,Any], need: InformationNeed)->bool:
    text=_text(row); entity=normalize_vietnamese(str(row.get('entity') or '')); param=normalize_vietnamese(str(row.get('parameter') or ''))
    return (not need.entity or need.entity in entity or need.entity in text) and (not need.parameter or need.parameter in param or need.parameter in text)

def build_candidate_union(retriever: Any, query: str, pages: list[dict[str,Any]]) -> list[dict[str,Any]]:
    """Union original regions and resolved TABLE_CELLs without suppressing cells."""
    base=retriever.allocate_budget_b_evidence(query,pages,max_units=5,table_aware=False)
    union={str(x['evidence_id']):dict(x) for x in base}
    for cell in retriever.table_resolver.resolve(query,pages[:5],max_facts=12,min_score=0.0): union[str(cell['evidence_id'])]=cell
    return list(union.values())

def select_structure_preserving(retriever: Any, query: str, pages: list[dict[str,Any]], max_units:int=5, policy:str='s4') -> list[dict[str,Any]]:
    candidates=build_candidate_union(retriever,query,pages); needs=extract_requirements(query,retriever.table_resolver.facts)
    selected=[]; covered=set(); seen_text=set()
    while candidates and len(selected)<max_units:
        best=None; best_value=-1e9
        for row in candidates:
            eid=str(row['evidence_id']); text=_text(row); gain=sum(1 for i,n in enumerate(needs) if i not in covered and _matches(row,n))
            # Existing allocator score makes the policy robust for non-table QA.
            relevance=float(row.get('allocated_score',0.0)); cell_bonus=3.0 if row.get('unit_type')=='TABLE_CELL' and gain else 0.0
            redundancy=-2.0 if text in seen_text else 0.0
            value=(4.0*gain + cell_bonus + relevance + redundancy) if policy=='s4' else (relevance + redundancy)
            if value>best_value: best,best_value=row,value
        if best is None: break
        selected.append(best); seen_text.add(_text(best));
        covered.update(i for i,n in enumerate(needs) if _matches(best,n)); candidates=[x for x in candidates if x['evidence_id']!=best['evidence_id']]
    if len(selected)<max_units:
        for row in retriever.allocate_budget_b_evidence(query,pages,max_units=max_units,table_aware=True):
            if row['evidence_id'] not in {x['evidence_id'] for x in selected}: selected.append(row)
            if len(selected)>=max_units: break
    return selected[:max_units]

def select_relation_aware(retriever: Any, query: str, pages: list[dict[str,Any]], max_units:int=5) -> list[dict[str,Any]]:
    """S5: count coverage only for typed MATCHED facts, otherwise safe A0 fallback."""
    candidates=build_candidate_union(retriever,query,pages); raw=extract_requirements(query,retriever.table_resolver.facts)
    reqs=[QuestionRequirement(n.entity,n.parameter,question_type=n.kind,confidence=.8) for n in raw]
    chosen=[]; covered=set()
    while candidates and len(chosen)<max_units:
        scored=[]
        for row in candidates:
            bindings=[bind(req,row) for req in reqs]; gain=sum(i not in covered and b.verdict==Verdict.MATCHED for i,b in enumerate(bindings))
            score=10*gain+float(row.get('allocated_score',0.0))+(2 if row.get('unit_type')=='TABLE_CELL' and gain else 0)
            scored.append((score,row,bindings))
        _,row,bindings=max(scored,key=lambda x:(x[0],str(x[1]['evidence_id']))); chosen.append(row)
        covered.update(i for i,b in enumerate(bindings) if b.verdict==Verdict.MATCHED);candidates=[x for x in candidates if x['evidence_id']!=row['evidence_id']]
    return chosen[:max_units]
