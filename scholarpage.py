from scholarly import scholarly
import difflib

def search_for_author_exact_match(author_name, similarity_threshold=0.8):
    search_query = scholarly.search_author(author_name)
    for potential_author in search_query:
        found_name = potential_author['name']
        similarity = difflib.SequenceMatcher(None, author_name.lower(), found_name.lower()).ratio()
        if similarity >= similarity_threshold:
            return scholarly.fill(potential_author, sections=['publications'])
    # No author found, fallback to keyword search
    print(f"No exact author match found for {author_name}. Performing keyword search...")
    keyword_search_results = []
    search_query = scholarly.search_pubs(author_name)
    try:
        for _ in range(3):  # Attempt to fetch up to 7 publications based on the keyword
            pub = next(search_query)
            if pub:  # Ensure the publication is valid
                keyword_search_results.append(pub)
    except StopIteration:
        pass  # No more results available

    publication_titles = [pub['bib']['title'] for pub in keyword_search_results if 'bib' in pub and 'title' in pub['bib']]

    # Now, if you want to print the names and titles
    #print({'name': author_name, 'publications': publication_titles})
    return({'name': author_name, 'publications': publication_titles})

def get_top_cited_papers(author_profile, top_n=7):
    if author_profile and 'publications' in author_profile:
        valid_publications = [pub for pub in author_profile['publications'] if isinstance(pub, dict)]
        sorted_publications = sorted(valid_publications, key=lambda x: x.get('num_citations', 0), reverse=True)
        top_publications = sorted_publications[:top_n]
        return [(pub['bib']['title'], pub.get('num_citations', '')) for pub in top_publications if 'bib' in pub and 'title' in pub['bib']]
    else:
        return []

#professor_name = "Ronald N. Goldman"
#author_profile = search_for_author_exact_match(professor_name)

#text_from_scholarly = " "

#if author_profile:
#    top_cited_papers = get_top_cited_papers(author_profile)
#    for title, citations in top_cited_papers:
#        text_from_scholarly += f"Title: {title}, Citations: {citations}\n"
#else:
#    text_from_scholarly = "Not available, replace this with information from google scrape"