"""
This is an optional step 3 of the pipeline. 

This step takes in the json object with research arxiv search terms that the template parser step provides and uses that with the arxiv api to fetch relevant papers. This step then cleans and summarizes that paper data by selecting the most relavent papers and adding them to the pipeline data.

This step is optional and can be skipped if the user does not want to include arxiv papers in the final email.
"""