"""
Template model for SQLAlchemy ORM.
Represents the templates table in the database.
"""


"""
Key fields: id, UUID to link to the user, template_content for the actual text, created at datetime

"""

# under the user we also need to add template_generations to track how many templates they have generated and remove from the zustand local storage from frontend. All tracked in the database