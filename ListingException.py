class ListingException(Exception):
    def __init__(self, message, listings):
        super().__init__(message)
        self.listings = listings