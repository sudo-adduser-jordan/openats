SELECT 
"url",
"company",
"apply_url",
"title",
"location",
"is_remote"
FROM jobs 
WHERE "country_iso" LIKE '%US%' 
AND "title" LIKE '%software%'
AND "title" NOT LIKE '%senior%'
AND "title" NOT LIKE '%director%'
AND "title" NOT LIKE '%sr.%'
AND "title" NOT LIKE '%sr %'
AND "title" NOT LIKE '%manager%'
AND "title" NOT LIKE '%principal%'
AND "title" NOT LIKE '%lead%'
AND "title" NOT LIKE '%vp,%'
AND "title" NOT LIKE '%vp of%'
AND "title" NOT LIKE '%vice%'
AND "title" NOT LIKE '%president%'
ORDER BY "is_remote" DESC
LIMIT 100