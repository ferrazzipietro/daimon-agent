from pocketflow import Flow
from nodes import (
    LoadSeeds,
    BuildQueries,
    SearchCandidates,
    AnalyzeCandidates,
    ScoreCandidates,
    ExtractContacts,
    DeduplicateCandidates,
    BuildShortlist,
    SaveOutputs,
)


def create_export_intelligence_flow():
    load = LoadSeeds()
    build_queries = BuildQueries()
    search = SearchCandidates()
    analyze = AnalyzeCandidates()
    score = ScoreCandidates()
    contacts = ExtractContacts()
    dedupe = DeduplicateCandidates()
    shortlist = BuildShortlist()
    save = SaveOutputs()

    load >> build_queries >> search >> analyze >> score >> contacts >> dedupe >> shortlist >> save

    return Flow(start=load)
