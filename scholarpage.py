from scholarly import scholarly
import difflib

def search_for_author_exact_match(author_name, similarity_threshold=0.8):
    print(f"[DEBUG] Starting search_for_author_exact_match for author: {author_name}")
    try:
        print("[DEBUG] Initiating scholarly.search_author")
        search_query = scholarly.search_author(author_name)
        print("[DEBUG] Successfully created search_query object")
        
        for potential_author in search_query:
            print(f"[DEBUG] Processing potential author: {potential_author.get('name', 'Unknown')}")
            found_name = potential_author['name']
            similarity = difflib.SequenceMatcher(None, author_name.lower(), found_name.lower()).ratio()
            print(f"[DEBUG] Similarity score: {similarity} for author: {found_name}")
            
            if similarity >= similarity_threshold:
                print(f"[DEBUG] Found matching author with similarity {similarity}. Filling author data...")
                try:
                    filled_author = scholarly.fill(potential_author, sections=['publications'])
                    print("[DEBUG] Successfully filled author data")
                    return filled_author
                except Exception as e:
                    print(f"[DEBUG] Error filling author data: {str(e)}")
                    raise e
                
        # No author found, fallback to keyword search
        print(f"[DEBUG] No exact author match found for {author_name}. Performing keyword search...")
        keyword_search_results = []
        print("[DEBUG] Initiating scholarly.search_pubs")
        search_query = scholarly.search_pubs(author_name)
        
        try:
            for i in range(3):  # Attempt to fetch up to 3 publications based on the keyword
                print(f"[DEBUG] Fetching publication {i+1}/3")
                pub = next(search_query)
                if pub:  # Ensure the publication is valid
                    print(f"[DEBUG] Found valid publication: {pub.get('bib', {}).get('title', 'Unknown title')}")
                    keyword_search_results.append(pub)
        except StopIteration:
            print("[DEBUG] No more publications available in search")
            pass  # No more results available
        except Exception as e:
            print(f"[DEBUG] Error during publication search: {str(e)}")
            raise e

        print(f"[DEBUG] Found {len(keyword_search_results)} publications in keyword search")
        publication_titles = [pub['bib']['title'] for pub in keyword_search_results if 'bib' in pub and 'title' in pub['bib']]
        print(f"[DEBUG] Extracted {len(publication_titles)} publication titles")

        result = {'name': author_name, 'publications': publication_titles}
        print("[DEBUG] Returning keyword search results")
        return result
        
    except Exception as e:
        print(f"[DEBUG] Critical error in search_for_author_exact_match: {str(e)}")
        raise e

def get_top_cited_and_recent_papers(author_profile, top_recent=4, top_cited=1):
    if author_profile and 'publications' in author_profile:
        # Filter valid publications with valid dictionaries
        valid_publications = [pub for pub in author_profile['publications'] if isinstance(pub, dict)]
        
        # Extract papers with valid publish dates and sort by the most recent
        recent_publications = [
            pub for pub in valid_publications if 'pub_year' in pub.get('bib', {}) and pub['bib']['pub_year'].isdigit()
        ]
        recent_publications = sorted(recent_publications, key=lambda x: int(x['bib']['pub_year']), reverse=True)
        
        # Select top N recent papers
        top_recent_publications = recent_publications[:top_recent]
        
        # Sort all valid publications by the most cited
        sorted_by_citations = sorted(valid_publications, key=lambda x: x.get('num_citations', 0), reverse=True)
        
        # Select top M most cited papers
        top_cited_publications = sorted_by_citations[:top_cited]
        
        # Combine the results, ensuring no duplicates
        unique_publications = {pub['bib']['title']: pub for pub in top_recent_publications + top_cited_publications}
        combined_publications = list(unique_publications.values())
        
        # Format the result as a list of (title, citations, year)
        return [
            (
                pub['bib']['title'],
                pub.get('num_citations', ''),
                pub['bib'].get('pub_year', 'N/A')
            )
            for pub in combined_publications if 'bib' in pub and 'title' in pub['bib']
        ]
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