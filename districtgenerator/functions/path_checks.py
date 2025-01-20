import os 

def check_path(path):
    """
    Check if a folder exists and return a unique path.
    If the folder doesn't exist, return the original path.
    If it exists, append a number to create a unique path.
    
    :param path: The original folder path to check
    :return: A unique folder path
    """
    if not os.path.exists(path):
        return path
    
    base_path = path
    counter = 1
    
    while os.path.exists(path):
        path = f"{base_path}_{counter}"
        counter += 1
    
    return path
