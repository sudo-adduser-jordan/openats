"""ATS collectors — one class per platform.

Each collector is a thin, dependency-light fetch+parse layer that returns
`Job` instances. Discovery, enrichment, deduplication, and publishing are
kept outside the public collector API so each collector stays usable on its own.

>>> from openats.collectors import GreenhouseCollector
>>> jobs = GreenhouseCollector("openai").fetch()
"""

from services._base import BaseCollector, CollectorRegistry, get_collector
from services.amazon import AmazonCollector
from services.apple import AppleCollector
from services.arbetsformedlingen import ArbetsformedlingenCollector
from services.ashby import AshbyCollector
from services.avature import AvatureCollector
from services.bamboohr import BambooHRCollector
from services.breezy import BreezyCollector
from services.builtin import BuiltInCollector
from services.bundesagentur import BundesagenturCollector
from services.cornerstone import CornerstoneCollector
from services.eightfold import EightfoldCollector
from services.eures import EuresCollector
from services.gem import GemCollector
from services.getonbrd import GetOnBrdCollector
from services.google import GoogleCollector
from services.greenhouse import GreenhouseCollector
from services.icims import iCIMSCollector
from services.infojobs_es import InfoJobsSpainCollector
from services.jazzhr import JazzHRCollector
from services.jobs_cz import JobsCzCollector
from services.jobsch import JobsChCollector
from services.join_com import JoinComCollector
from services.lever import LeverCollector
from services.manfred import ManfredCollector
from services.mercor import MercorCollector
from services.meta import MetaCollector
from services.oracle import OracleCollector
from services.personio import PersonioCollector
from services.phenom import PhenomCollector
from services.pinpoint import PinpointCollector
from services.programathor import ProgramathorCollector
from services.recruitee import RecruiteeCollector
from services.recruiterbox import RecruiterboxCollector
from services.remoteok import RemoteOKCollector
from services.rippling import RipplingCollector
from services.smartrecruiters import SmartRecruitersCollector
from services.successfactors import SuccessFactorsCollector
from services.taleo import TaleoCollector
from services.teamtailor import TeamtailorCollector
from services.tesla import TeslaCollector
from services.thehub import TheHubCollector
from services.tiktok import TikTokCollector
from services.uber import UberCollector
from services.usajobs import USAJobsCollector
from services.wanted import WantedCollector
from services.welcometothejungle import WTTJCollector
from services.wellfound import WellfoundCollector
from services.weworkremotely import WeWorkRemotelyCollector
from services.workable import WorkableCollector
from services.workday import WorkdayCollector
from services.ycombinator import YCombinatorCollector

__all__ = [
    "AmazonCollector",
    "AppleCollector",
    "ArbetsformedlingenCollector",
    "AshbyCollector",
    "AvatureCollector",
    "BambooHRCollector",
    "BaseCollector",
    "BreezyCollector",
    "BuiltInCollector",
    "BundesagenturCollector",
    "CollectorRegistry",
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
    "get_collector",
    "iCIMSCollector",
]
