"""ATS collectors — one class per platform.

Each collector is a thin, dependency-light fetch+parse layer that returns
`Job` instances. Discovery, enrichment, deduplication, and publishing are
kept outside the public collector API so each collector stays usable on its own.

>>> from services.collect import GreenhouseCollector
>>> jobs = GreenhouseCollector("openai").fetch()
"""

from services.collect.amazon import AmazonCollector
from services.collect.apple import AppleCollector
from services.collect.arbetsformedlingen import ArbetsformedlingenCollector
from services.collect.ashby import AshbyCollector
from services.collect.avature import AvatureCollector
from services.collect.bamboohr import BambooHRCollector
from services.collect.breezy import BreezyCollector
from services.collect.builtin import BuiltInCollector
from services.collect.bundesagentur import BundesagenturCollector
from services.collect.cornerstone import CornerstoneCollector
from services.collect.eightfold import EightfoldCollector
from services.collect.eures import EuresCollector
from services.collect.gem import GemCollector
from services.collect.getonbrd import GetOnBrdCollector
from services.collect.google import GoogleCollector
from services.collect.greenhouse import GreenhouseCollector
from services.collect.icims import iCIMSCollector
from services.collect.infojobs_es import InfoJobsSpainCollector
from services.collect.jazzhr import JazzHRCollector
from services.collect.jobs_cz import JobsCzCollector
from services.collect.jobsch import JobsChCollector
from services.collect.join_com import JoinComCollector
from services.collect.lever import LeverCollector
from services.collect.manfred import ManfredCollector
from services.collect.mercor import MercorCollector
from services.collect.meta import MetaCollector
from services.collect.oracle import OracleCollector
from services.collect.personio import PersonioCollector
from services.collect.phenom import PhenomCollector
from services.collect.pinpoint import PinpointCollector
from services.collect.programathor import ProgramathorCollector
from services.collect.recruitee import RecruiteeCollector
from services.collect.recruiterbox import RecruiterboxCollector
from services.collect.remoteok import RemoteOKCollector
from services.collect.rippling import RipplingCollector
from services.collect.smartrecruiters import SmartRecruitersCollector
from services.collect.successfactors import SuccessFactorsCollector
from services.collect.taleo import TaleoCollector
from services.collect.teamtailor import TeamtailorCollector
from services.collect.tesla import TeslaCollector
from services.collect.thehub import TheHubCollector
from services.collect.tiktok import TikTokCollector
from services.collect.uber import UberCollector
from services.collect.usajobs import USAJobsCollector
from services.collect.wanted import WantedCollector
from services.collect.welcometothejungle import WTTJCollector
from services.collect.wellfound import WellfoundCollector
from services.collect.weworkremotely import WeWorkRemotelyCollector
from services.collect.workable import WorkableCollector
from services.collect.workday import WorkdayCollector
from services.collect.ycombinator import YCombinatorCollector

__all__ = [
    "AmazonCollector",
    "AppleCollector",
    "ArbetsformedlingenCollector",
    "AshbyCollector",
    "AvatureCollector",
    "BambooHRCollector",
    "BreezyCollector",
    "BuiltInCollector",
    "BundesagenturCollector",
    "CornerstoneCollector",
    "EightfoldCollector",
    "EuresCollector",
    "GemCollector",
    "GetOnBrdCollector",
    "GoogleCollector",
    "GreenhouseCollector",
    "InfoJobsSpainCollector",
    "JazzHRCollector",
    "JobsChCollector",
    "JobsCzCollector",
    "JoinComCollector",
    "LeverCollector",
    "ManfredCollector",
    "MercorCollector",
    "MetaCollector",
    "OracleCollector",
    "PersonioCollector",
    "PhenomCollector",
    "PinpointCollector",
    "ProgramathorCollector",
    "RecruiteeCollector",
    "RecruiterboxCollector",
    "RemoteOKCollector",
    "RipplingCollector",
    "SmartRecruitersCollector",
    "SuccessFactorsCollector",
    "TaleoCollector",
    "TeamtailorCollector",
    "TeslaCollector",
    "TheHubCollector",
    "TikTokCollector",
    "USAJobsCollector",
    "UberCollector",
    "WTTJCollector",
    "WantedCollector",
    "WeWorkRemotelyCollector",
    "WellfoundCollector",
    "WorkableCollector",
    "WorkdayCollector",
    "YCombinatorCollector",
    "iCIMSCollector",
]
