from scholarly import scholarly, ProxyGenerator
import difflib
import time
from functools import wraps
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

def timeout(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set the signal handler and a timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                # Disable the alarm
                signal.alarm(0)
            return result
        return wrapper
    return decorator

def safe_next(iterator, timeout_secs=10):
    """Safely get next item from iterator with timeout"""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_secs)
    try:
        item = next(iterator)
        signal.alarm(0)
        return item
    except StopIteration:
        signal.alarm(0)
        raise
    except TimeoutError:
        signal.alarm(0)
        raise TimeoutError(f"Iterator next() operation timed out after {timeout_secs} seconds")
    except Exception as e:
        signal.alarm(0)
        raise

def search_for_author_exact_match(author_name, similarity_threshold=0.8):
    print(f"[DEBUG] Starting search_for_author_exact_match for author: {author_name}")
    
    # Set up proxy to avoid blocking
    try:
        pg = ProxyGenerator()
        success = pg.FreeProxies()
        if success:
            scholarly.use_proxy(pg)
            print("[DEBUG] Successfully set up proxy")
        else:
            print("[DEBUG] Failed to set up proxy, continuing without one")
    except Exception as e:
        print(f"[DEBUG] Error setting up proxy: {str(e)}")
    
    try:
        print("[DEBUG] Initiating scholarly.search_author")
        search_query = scholarly.search_author(author_name)
        print("[DEBUG] Successfully created search_query object")
        
        authors_found = 0
        max_authors_to_check = 5
        
        while authors_found < max_authors_to_check:
            try:
                print(f"[DEBUG] Attempting to fetch author {authors_found + 1}/{max_authors_to_check}")
                potential_author = safe_next(search_query, timeout_secs=15)
                authors_found += 1
                
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
                        # Continue to keyword search instead of raising
                        break
                
            except TimeoutError as te:
                print(f"[DEBUG] Timeout while fetching author: {str(te)}")
                break
            except StopIteration:
                print("[DEBUG] No more authors to process")
                break
            except Exception as e:
                print(f"[DEBUG] Error processing author: {str(e)}")
                break
        
        # No author found or error occurred, fallback to keyword search
        print(f"[DEBUG] No exact author match found for {author_name}. Performing keyword search...")
        keyword_search_results = []
        print("[DEBUG] Initiating scholarly.search_pubs")
        
        try:
            search_query = scholarly.search_pubs(author_name)
            for i in range(3):  # Attempt to fetch up to 3 publications
                try:
                    print(f"[DEBUG] Fetching publication {i+1}/3")
                    pub = safe_next(search_query, timeout_secs=15)
                    if pub:
                        print(f"[DEBUG] Found valid publication: {pub.get('bib', {}).get('title', 'Unknown title')}")
                        keyword_search_results.append(pub)
                except TimeoutError:
                    print(f"[DEBUG] Timeout while fetching publication {i+1}")
                    break
                except StopIteration:
                    print("[DEBUG] No more publications available")
                    break
                except Exception as e:
                    print(f"[DEBUG] Error fetching publication: {str(e)}")
                    break
                    
        except Exception as e:
            print(f"[DEBUG] Error during publication search: {str(e)}")
        
        print(f"[DEBUG] Found {len(keyword_search_results)} publications in keyword search")
        publication_titles = [pub['bib']['title'] for pub in keyword_search_results if 'bib' in pub and 'title' in pub['bib']]
        print(f"[DEBUG] Extracted {len(publication_titles)} publication titles")
        
        result = {'name': author_name, 'publications': publication_titles}
        print("[DEBUG] Returning keyword search results")
        return result
        
    except Exception as e:
        print(f"[DEBUG] Critical error in search_for_author_exact_match: {str(e)}")
        return {'name': author_name, 'publications': []}

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