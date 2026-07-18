SELECT * FROM jobs 
WHERE "title" LIKE '%software%'
AND "title" LIKE '%junior%'
AND "title" NOT LIKE '%senior%'
AND "title" NOT LIKE '%director%'
AND "title" NOT LIKE '%sr.%'
AND "title" NOT LIKE '%sr %'
AND "title" NOT LIKE '%manager%'
AND "title" NOT LIKE '%principal%'
AND "title" NOT LIKE '%lead%'
AND "title" NOT LIKE '%vp of%'
AND  "country_iso" like '%US%' 
ORDER BY "is_remote"
