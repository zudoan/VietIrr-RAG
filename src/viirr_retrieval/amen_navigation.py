"""Bounded, deterministic Active Evidence Navigation (AMEN-RAG experiment)."""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Any
from viirr_retrieval.need_aware_selection import extract_requirements
from viirr_retrieval.relation_binding import QuestionRequirement, Verdict, bind

@dataclass
class NavigationTrace:
 actions:list[dict[str,Any]]=field(default_factory=list)
 selected_pages:list[dict[str,Any]]=field(default_factory=list)
 evidence:list[dict[str,Any]]=field(default_factory=list)

class ActiveEvidenceNavigator:
 """Search→open→inspect controller; no LLM planning and no gold access."""
 def __init__(self,retriever:Any,max_rounds:int=2,max_open_pages:int=8,max_evidence:int=5):
  self.r=retriever;self.max_rounds=max_rounds;self.max_open_pages=max_open_pages;self.max_evidence=max_evidence
 def search_documents(self,query:str)->list[dict[str,Any]]:
  pages=self.r.retrieve_candidates(query,120,True,True,True,True);self._trace.actions.append({'tool':'search_documents','count':len(pages)});return pages
 def open_page(self,page:dict[str,Any])->dict[str,Any]:
  p=self.r.pages[page['page_index']];self._trace.actions.append({'tool':'open_page','page_id':p['page_id']});return p
 def inspect_regions(self,page:dict[str,Any])->list[dict[str,Any]]:
  ids=self.r.page_to_unit_indices.get(page['page_id'],[]);rows=[self.r.units[i] for i in ids];self._trace.actions.append({'tool':'inspect_regions','page_id':page['page_id'],'count':len(rows)});return rows
 def inspect_table(self,table_id:str)->list[dict[str,Any]]:
  facts=self.r.table_resolver.facts_by_table.get(table_id,[]);self._trace.actions.append({'tool':'inspect_table','table_id':table_id,'count':len(facts)});return [f.to_evidence_dict(0.,0) for f in facts]
 def build_rerank_shortlist(self,initial:list[dict[str,Any]],supplementary:list[dict[str,Any]],budget:int=60)->list[dict[str,Any]]:
  """Deterministic 40/20 admission; all returned pages are scored in one CE call."""
  initial_unique={x['page_id']:x for x in initial}; extra=[x for x in supplementary if x['page_id'] not in initial_unique]
  initial_slots=min(len(initial_unique),max(0,budget-min(20,len(extra))))
  return list(initial_unique.values())[:initial_slots]+extra[:budget-initial_slots]
 def run(self,query:str)->NavigationTrace:
  self._trace=NavigationTrace();pool=self.search_documents(query);ranked=self.r.rerank_candidates(query,pool,60,enhanced_mode=True,table_aware=True)
  opened=set()
  for page in ranked:
   if len(opened)>=self.max_open_pages:break
   p=self.open_page(page)
   if p['page_id'] not in opened:self.inspect_regions(p);opened.add(p['page_id']);self._trace.selected_pages.append(page)
  evidence=[] if self.max_open_pages==0 else self.r.allocate_budget_b_evidence(query,ranked,self.max_evidence,table_aware=True)
  # Only unsatisfied typed requirements trigger an additional, deduplicated search.
  resolver=getattr(self.r,'table_resolver',None);needs=extract_requirements(query,getattr(resolver,'facts',[]));seen={query}
  for need in needs[:self.max_rounds]:
   req=QuestionRequirement(need.entity,need.parameter)
   if any(bind(req,e).verdict==Verdict.MATCHED for e in evidence):continue
   follow=' '.join(x for x in (need.entity,need.parameter) if x)
   if not follow or follow in seen:continue
   seen.add(follow);extra=self.search_documents(follow)[:10]
   self._trace.actions.append({'tool':'supplementary_search','query':follow,'new_candidates':len(extra)})
   for page in extra:
    if len(opened)>=self.max_open_pages:break
    p=self.open_page(page)
    if p['page_id'] not in opened:self.inspect_regions(p);opened.add(p['page_id']);self._trace.selected_pages.append(page)
   # Scores from independent rounds are not comparable: rerank the deduplicated union.
   shortlist=self.build_rerank_shortlist(pool,extra,60)
   self._trace.actions.append({'tool':'admit_rerank_shortlist','initial':len(pool),'supplementary':len(extra),'admitted':len(shortlist)})
   ranked=self.r.rerank_candidates(query,shortlist,len(shortlist),enhanced_mode=True,table_aware=True)
   evidence=self.r.allocate_budget_b_evidence(query,ranked,self.max_evidence,table_aware=True)
  self._trace.evidence=evidence;self._trace.actions.append({'tool':'verify','evidence_count':len(evidence),'rounds_used':1})
  return self._trace
