#!/bin/bash
# Extract individual HBR articles from the collection into ~/Vaults/Wiki/raw/

SRC="/Users/andysparks/Documents/Claude/projects/sourceconvert/output/HBR_s 10 Must Reads for New Managers Collection.md"
RAW="$HOME/Vaults/Wiki/raw"
CONVERT="/Users/andysparks/Documents/Claude/projects/sourceconvert/convert.py"
COUNT=0

# Step 1: Save full collection as one raw file
echo "=== Creating full collection file ==="
cat > "$RAW/hbr-10-must-reads-new-managers-collection.md" << 'FRONTMATTER'
---
title: "HBR's 10 Must Reads for New Managers Collection (4 Books)"
authors:
  - "[[Harvard Business Review]]"
year: 2017
url:
isbn:
publisher: Harvard Business Review
status: complete
topics:
  - new-manager
  - leadership
  - performance-management
  - self-management
  - cross-cultural
  - team-dynamics
  - delegation
  - motivation
  - trust
type: book
tags:
  - hbr-collection
  - management
  - leadership
source_of:
clipped: 2026-04-06
clipped_by: claude
---

FRONTMATTER
cat "$SRC" >> "$RAW/hbr-10-must-reads-new-managers-collection.md"
python3 "$CONVERT" "$RAW/hbr-10-must-reads-new-managers-collection.md" --clean
COUNT=$((COUNT + 1))
echo ""

# Helper function to extract an article
extract_article() {
    local start=$1
    local end=$2
    local filename=$3
    local title="$4"
    local authors="$5"
    local topics="$6"
    local tags="$7"
    local year="${8:-}"

    echo "=== Extracting: $title ==="

    # Build authors YAML (handle multiple authors separated by |)
    local authors_yaml=""
    IFS='|' read -ra AUTHOR_ARRAY <<< "$authors"
    for author in "${AUTHOR_ARRAY[@]}"; do
        authors_yaml="${authors_yaml}  - \"[[${author}]]\"\n"
    done

    # Build topics YAML
    local topics_yaml=""
    IFS='|' read -ra TOPIC_ARRAY <<< "$topics"
    for topic in "${TOPIC_ARRAY[@]}"; do
        topics_yaml="${topics_yaml}  - ${topic}\n"
    done

    # Build tags YAML
    local tags_yaml=""
    IFS='|' read -ra TAG_ARRAY <<< "$tags"
    for tag in "${TAG_ARRAY[@]}"; do
        tags_yaml="${tags_yaml}  - ${tag}\n"
    done

    # Write frontmatter
    printf -- "---\ntitle: \"${title}\"\nauthors:\n${authors_yaml}year: ${year}\nurl:\npublisher: Harvard Business Review\nstatus: chapter\ntopics:\n${topics_yaml}type: article\ntags:\n${tags_yaml}parent_work: \"[[hbr-10-must-reads-new-managers-collection]]\"\nclipped: 2026-04-06\nclipped_by: claude\n---\n\n" > "$RAW/$filename"

    # Extract lines and append
    sed -n "${start},${end}p" "$SRC" >> "$RAW/$filename"

    # Run clean
    python3 "$CONVERT" "$RAW/$filename" --clean
    COUNT=$((COUNT + 1))
    echo ""
}

# ============================================================
# BOOK 1: New Managers
# ============================================================

extract_article 184 1013 \
    "hbr-hill-becoming-the-boss.md" \
    "Becoming the Boss" \
    "Linda A. Hill" \
    "new-manager|leadership|self-management" \
    "hbr|new-manager-transition|identity" \
    "2007"

extract_article 1014 1563 \
    "hbr-watkins-leading-team-you-inherit.md" \
    "Leading the Team You Inherit" \
    "Michael D. Watkins" \
    "new-manager|team-dynamics|leadership" \
    "hbr|team-assessment|new-manager-transition" \
    "2016"

extract_article 1564 2093 \
    "hbr-walker-saving-rookie-managers.md" \
    "Saving Your Rookie Managers from Themselves" \
    "Carol A. Walker" \
    "new-manager|delegation|performance-management" \
    "hbr|new-manager-transition|coaching" \
    "2002"

extract_article 2094 2456 \
    "hbr-reid-ramarajan-high-intensity-workplace.md" \
    "Managing the High-Intensity Workplace" \
    "Erin Reid|Lakshmi Ramarajan" \
    "self-management|leadership|trust" \
    "hbr|work-life|culture" \
    "2016"

extract_article 2457 3207 \
    "hbr-cialdini-science-of-persuasion.md" \
    "Harnessing the Science of Persuasion" \
    "Robert B. Cialdini" \
    "leadership|trust|motivation" \
    "hbr|influence|persuasion" \
    "2001"

extract_article 3208 3977 \
    "hbr-goleman-what-makes-a-leader.md" \
    "What Makes a Leader?" \
    "Daniel Goleman" \
    "leadership|self-management|performance-management" \
    "hbr|emotional-intelligence|leadership" \
    "1998"

extract_article 3978 4434 \
    "hbr-ibarra-authenticity-paradox.md" \
    "The Authenticity Paradox" \
    "Herminia Ibarra" \
    "leadership|self-management|new-manager" \
    "hbr|identity|leadership-development" \
    "2015"

extract_article 4435 5081 \
    "hbr-gabarro-kotter-managing-your-boss.md" \
    "Managing Your Boss" \
    "John J. Gabarro|John P. Kotter" \
    "delegation|trust|leadership" \
    "hbr|managing-up|relationships" \
    "1980"

extract_article 5082 5652 \
    "hbr-ibarra-hunter-leaders-networks.md" \
    "How Leaders Create and Use Networks" \
    "Herminia Ibarra|Mark Lee Hunter" \
    "leadership|self-management|new-manager" \
    "hbr|networking|leadership-development" \
    "2007"

# SKIP: Management Time: Who's Got the Monkey? (already in raw/)

extract_article 6137 6661 \
    "hbr-watkins-how-managers-become-leaders.md" \
    "How Managers Become Leaders" \
    "Michael D. Watkins" \
    "new-manager|leadership|self-management" \
    "hbr|leadership-transition|new-manager-transition" \
    "2012"

# ============================================================
# BOOK 2: Managing People
# ============================================================

extract_article 7180 8049 \
    "hbr-goleman-leadership-that-gets-results.md" \
    "Leadership That Gets Results" \
    "Daniel Goleman" \
    "leadership|performance-management|motivation" \
    "hbr|leadership-styles|emotional-intelligence" \
    "2000"

extract_article 8050 8662 \
    "hbr-herzberg-motivate-employees.md" \
    "One More Time: How Do You Motivate Employees?" \
    "Frederick Herzberg" \
    "motivation|performance-management|leadership" \
    "hbr|motivation|hygiene-factors" \
    "1968"

extract_article 8663 9472 \
    "hbr-manzoni-barsoux-setup-to-fail.md" \
    "The Set-Up-to-Fail Syndrome" \
    "Jean-Francois Manzoni|Jean-Louis Barsoux" \
    "performance-management|trust|leadership" \
    "hbr|feedback|manager-employee-dynamics" \
    "1998"

# SKIP: Saving Your Rookie Managers (duplicate)

extract_article 9934 10577 \
    "hbr-buckingham-what-great-managers-do.md" \
    "What Great Managers Do" \
    "Marcus Buckingham" \
    "leadership|performance-management|motivation" \
    "hbr|strengths|individualization" \
    "2005"

extract_article 10578 11292 \
    "hbr-kim-mauborgne-fair-process.md" \
    "Fair Process: Managing in the Knowledge Economy" \
    "W. Chan Kim|Renee Mauborgne" \
    "trust|leadership|performance-management|motivation" \
    "hbr|fairness|procedural-justice" \
    "1997"

extract_article 11293 12047 \
    "hbr-argyris-teaching-smart-people.md" \
    "Teaching Smart People How to Learn" \
    "Chris Argyris" \
    "performance-management|self-management|leadership" \
    "hbr|learning|defensive-reasoning" \
    "1991"

extract_article 12048 12620 \
    "hbr-banaji-bazerman-chugh-unethical.md" \
    "How (Un)ethical Are You?" \
    "Mahzarin R. Banaji|Max H. Bazerman|Dolly Chugh" \
    "trust|leadership|self-management" \
    "hbr|ethics|implicit-bias" \
    "2003"

extract_article 12621 13285 \
    "hbr-katzenbach-smith-discipline-of-teams.md" \
    "The Discipline of Teams" \
    "Jon R. Katzenbach|Douglas K. Smith" \
    "team-dynamics|leadership|performance-management" \
    "hbr|teams|team-performance" \
    "1993"

# SKIP: Managing Your Boss (duplicate)

# ============================================================
# BOOK 3: Managing Yourself
# ============================================================

extract_article 14561 14955 \
    "hbr-christensen-measure-your-life.md" \
    "How Will You Measure Your Life?" \
    "Clayton M. Christensen" \
    "self-management|leadership" \
    "hbr|purpose|life-strategy" \
    "2010"

extract_article 14956 15615 \
    "hbr-drucker-managing-oneself.md" \
    "Managing Oneself" \
    "Peter F. Drucker" \
    "self-management|leadership|new-manager" \
    "hbr|self-awareness|strengths" \
    "1999"

# SKIP: Management Time: Who's Got the Monkey? (duplicate, already in raw/)

extract_article 16051 16532 \
    "hbr-coutu-how-resilience-works.md" \
    "How Resilience Works" \
    "Diane L. Coutu" \
    "self-management|leadership" \
    "hbr|resilience|adversity" \
    "2002"

extract_article 16533 17134 \
    "hbr-schwartz-mccarthy-manage-energy.md" \
    "Manage Your Energy, Not Your Time" \
    "Tony Schwartz|Catherine McCarthy" \
    "self-management|performance-management|motivation" \
    "hbr|energy-management|productivity" \
    "2007"

extract_article 17135 17703 \
    "hbr-hallowell-overloaded-circuits.md" \
    "Overloaded Circuits" \
    "Edward M. Hallowell" \
    "self-management|performance-management" \
    "hbr|attention|cognitive-overload" \
    "2005"

extract_article 17704 18217 \
    "hbr-friedman-better-leader-richer-life.md" \
    "Be a Better Leader, Have a Richer Life" \
    "Stewart D. Friedman" \
    "self-management|leadership" \
    "hbr|work-life|total-leadership" \
    "2008"

extract_article 18218 18628 \
    "hbr-ghoshal-bruch-reclaim-your-job.md" \
    "Reclaim Your Job" \
    "Sumantra Ghoshal|Heike Bruch" \
    "self-management|leadership|delegation" \
    "hbr|agency|purposeful-action" \
    "2004"

extract_article 18629 19156 \
    "hbr-quinn-moments-of-greatness.md" \
    "Moments of Greatness: Entering the Fundamental State of Leadership" \
    "Robert E. Quinn" \
    "leadership|self-management" \
    "hbr|fundamental-state|leadership-presence" \
    "2005"

extract_article 19157 19802 \
    "hbr-kaplan-person-in-the-mirror.md" \
    "What to Ask the Person in the Mirror" \
    "Robert S. Kaplan" \
    "leadership|self-management" \
    "hbr|self-reflection|leadership-questions" \
    "2007"

extract_article 19803 20496 \
    "hbr-goleman-boyatzis-mckee-primal-leadership.md" \
    "Primal Leadership: The Hidden Driver of Great Performance" \
    "Daniel Goleman|Richard Boyatzis|Annie McKee" \
    "leadership|self-management|team-dynamics" \
    "hbr|emotional-intelligence|resonant-leadership" \
    "2001"

# ============================================================
# BOOK 4: Managing Across Cultures
# ============================================================

extract_article 21196 21816 \
    "hbr-earley-mosakowski-cultural-intelligence.md" \
    "Cultural Intelligence" \
    "P. Christopher Earley|Elaine Mosakowski" \
    "cross-cultural|leadership|self-management" \
    "hbr|cultural-intelligence|global-leadership" \
    "2004"

extract_article 21817 22476 \
    "hbr-brett-behfar-kern-multicultural-teams.md" \
    "Managing Multicultural Teams" \
    "Jeanne Brett|Kristin Behfar|Mary C. Kern" \
    "cross-cultural|team-dynamics|leadership" \
    "hbr|multicultural-teams|conflict-resolution" \
    "2006"

extract_article 22477 22930 \
    "hbr-hong-doz-loreal-multiculturalism.md" \
    "L'Oreal Masters Multiculturalism" \
    "Hae-Jung Hong|Yves L. Doz" \
    "cross-cultural|team-dynamics|leadership" \
    "hbr|diversity|organizational-culture" \
    "2013"

extract_article 22931 24003 \
    "hbr-thomas-ely-making-differences-matter.md" \
    "Making Differences Matter: A New Paradigm for Managing Diversity" \
    "David A. Thomas|Robin J. Ely" \
    "cross-cultural|team-dynamics|leadership|trust" \
    "hbr|diversity|inclusion" \
    "1996"

extract_article 24004 24354 \
    "hbr-meyer-cultural-minefield.md" \
    "Navigating the Cultural Minefield" \
    "Erin Meyer" \
    "cross-cultural|leadership|trust" \
    "hbr|culture-map|cross-cultural-communication" \
    "2014"

extract_article 24355 25060 \
    "hbr-donaldson-values-in-tension.md" \
    "Values in Tension: Ethics Away from Home" \
    "Thomas Donaldson" \
    "cross-cultural|trust|leadership" \
    "hbr|ethics|global-business-ethics" \
    "1996"

extract_article 25061 25561 \
    "hbr-neeley-global-business-english.md" \
    "Global Business Speaks English" \
    "Tsedal Neeley" \
    "cross-cultural|leadership|team-dynamics" \
    "hbr|language|globalization" \
    "2012"

extract_article 25562 25980 \
    "hbr-wilson-doz-managing-global-innovation.md" \
    "10 Rules for Managing Global Innovation" \
    "Keeley Wilson|Yves L. Doz" \
    "cross-cultural|team-dynamics|leadership" \
    "hbr|innovation|global-teams" \
    "2012"

extract_article 25981 26340 \
    "hbr-trompenaars-woolliams-lost-in-translation.md" \
    "Lost in Translation" \
    "Fons Trompenaars|Peter Woolliams" \
    "cross-cultural|leadership|trust" \
    "hbr|cultural-dilemmas|cross-cultural-communication" \
    "2011"

extract_article 26341 26913 \
    "hbr-black-gregersen-managing-expats.md" \
    "The Right Way to Manage Expats" \
    "J. Stewart Black|Hal B. Gregersen" \
    "cross-cultural|leadership|performance-management" \
    "hbr|expatriates|global-assignments" \
    "1999"

echo "=== DONE ==="
echo "Total files created: $COUNT"
