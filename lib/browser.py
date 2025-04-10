"""Browser utilities for Selenium automation"""
import os
import glob
from typing import Optional
import logging
from selenium import webdriver

def get_firefox_profile_path(logger=None, config=None) -> Optional[str]:
    """Get the default Firefox profile path
    
    Args:
        logger: Optional logger instance
        config: Optional configuration dictionary that may contain FIREFOX_PROFILE
        
    Returns:
        Path to Firefox profile or None if not found
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        # Firefox profiles location on Windows
        firefox_data_dir = os.path.join(os.environ['APPDATA'], 'Mozilla', 'Firefox', 'Profiles')
        
        if not os.path.exists(firefox_data_dir):
            logger.warning(f"Firefox profiles directory not found: {firefox_data_dir}")
            return None
        
        # Check if a specific profile is configured
        if config and 'FIREFOX_PROFILE' in config:
            preferred_profile = config['FIREFOX_PROFILE']
            # Try to find the specified profile
            for profile_dir in os.listdir(firefox_data_dir):
                profile_path = os.path.join(firefox_data_dir, profile_dir)
                if os.path.isdir(profile_path) and preferred_profile in profile_path:
                    logger.info(f"Using configured Firefox profile: {profile_path}")
                    return profile_path
            logger.warning(f"Configured profile '{preferred_profile}' not found")
            
        # Look for profiles.ini to find the default profile
        profiles_ini_path = os.path.join(os.environ['APPDATA'], 'Mozilla', 'Firefox', 'profiles.ini')
        
        if os.path.exists(profiles_ini_path):
            # Parse profiles.ini to find the default profile
            default_profile = None
            current_section = None
            is_default = False
            profile_path = None
            
            with open(profiles_ini_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('[') and line.endswith(']'):
                        # If we found a default profile in the previous section, use it
                        if is_default and profile_path:
                            default_profile = profile_path
                            break
                        # Start a new section
                        current_section = line[1:-1]
                        is_default = False
                        profile_path = None
                    elif current_section and current_section.startswith('Profile'):
                        if line.startswith('Default=1'):
                            is_default = True
                        elif line.startswith('Path='):
                            profile_path = line.split('=', 1)[1]
            
            # Check the last section too
            if is_default and profile_path and not default_profile:
                default_profile = profile_path
            
            if default_profile:
                # Check if it's a relative or absolute path
                if not os.path.isabs(default_profile):
                    # Make sure to use the correct path separator
                    default_profile = os.path.join(os.path.dirname(profiles_ini_path), default_profile)
                
                logger.info(f"Found default Firefox profile: {default_profile}")
                return default_profile
        
        # Fallback: use the profile with "default-release" in the name
        for profile_dir in os.listdir(firefox_data_dir):
            if "default-release" in profile_dir:
                profile_path = os.path.join(firefox_data_dir, profile_dir)
                logger.info(f"Using default-release Firefox profile: {profile_path}")
                return profile_path
        
        # Second fallback: just use the most recently modified profile directory
        profile_dirs = glob.glob(os.path.join(firefox_data_dir, "*.*"))
        if profile_dirs:
            # Sort by modification time (newest first)
            profile_dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            logger.info(f"Using most recent Firefox profile: {profile_dirs[0]}")
            return profile_dirs[0]
            
        logger.warning("No Firefox profiles found")
        return None
        
    except Exception as e:
        logger.error(f"Error finding Firefox profile: {str(e)}")
        return None

def get_chrome_profile_path(logger=None, config=None) -> Optional[str]:
    """Get the default Chrome profile path
    
    Args:
        logger: Optional logger instance
        config: Optional configuration dictionary that may contain CHROME_PROFILE
        
    Returns:
        Path to Chrome profile or None if not found
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        # Chrome profiles location on Windows
        chrome_data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'Google', 'Chrome', 'User Data')
        
        if not os.path.exists(chrome_data_dir):
            logger.warning(f"Chrome profiles directory not found: {chrome_data_dir}")
            return None
        
        # Check if a specific profile is configured
        if config and 'CHROME_PROFILE' in config:
            preferred_profile = config['CHROME_PROFILE']
            profile_path = os.path.join(chrome_data_dir, preferred_profile)
            
            if os.path.isdir(profile_path):
                logger.info(f"Using configured Chrome profile: {profile_path}")
                return profile_path
            logger.warning(f"Configured Chrome profile '{preferred_profile}' not found")
        
        # Default to 'Default' profile if it exists
        default_profile = os.path.join(chrome_data_dir, 'Default')
        if os.path.isdir(default_profile):
            logger.info(f"Using default Chrome profile: {default_profile}")
            return default_profile
            
        # Look for any profile directory
        profile_dirs = [d for d in os.listdir(chrome_data_dir) 
                       if os.path.isdir(os.path.join(chrome_data_dir, d)) and 
                       (d.startswith('Profile') or d == 'Default')]
        
        if profile_dirs:
            # Sort by modification time (newest first)
            profile_dirs.sort(key=lambda x: os.path.getmtime(os.path.join(chrome_data_dir, x)), reverse=True)
            profile_path = os.path.join(chrome_data_dir, profile_dirs[0])
            logger.info(f"Using Chrome profile: {profile_path}")
            return profile_path
            
        logger.warning("No Chrome profiles found")
        return None
        
    except Exception as e:
        logger.error(f"Error finding Chrome profile: {str(e)}")
        return None

def get_edge_profile_path(logger=None, config=None) -> Optional[str]:
    """Get the default Edge profile path
    
    Args:
        logger: Optional logger instance
        config: Optional configuration dictionary that may contain EDGE_PROFILE
        
    Returns:
        Path to Edge profile or None if not found
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        # Edge profiles location on Windows
        edge_data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Edge', 'User Data')
        
        if not os.path.exists(edge_data_dir):
            logger.warning(f"Edge profiles directory not found: {edge_data_dir}")
            return None
        
        # Check if a specific profile is configured
        if config and 'EDGE_PROFILE' in config:
            preferred_profile = config['EDGE_PROFILE']
            
            # First try exact match
            profile_path = os.path.join(edge_data_dir, preferred_profile)
            if os.path.isdir(profile_path):
                logger.info(f"Using configured Edge profile: {profile_path}")
                return edge_data_dir  # Return the User Data directory for Edge
            
            # Try to find a profile that contains the preferred name
            for profile_dir in os.listdir(edge_data_dir):
                profile_path = os.path.join(edge_data_dir, profile_dir)
                if os.path.isdir(profile_path) and preferred_profile.lower() in profile_dir.lower():
                    logger.info(f"Found matching Edge profile: {profile_dir}")
                    return edge_data_dir  # Return the User Data directory for Edge
                
                # Check Local State file for profile name
                local_state_path = os.path.join(profile_path, 'Local State')
                if os.path.exists(local_state_path):
                    try:
                        import json
                        with open(local_state_path, 'r', encoding='utf-8') as f:
                            local_state = json.load(f)
                            profile_name = local_state.get('profile', {}).get('name', '')
                            if preferred_profile.lower() in profile_name.lower():
                                logger.info(f"Found Edge profile with name '{profile_name}' in {profile_dir}")
                                return edge_data_dir  # Return the User Data directory for Edge
                    except Exception as e:
                        logger.warning(f"Error reading Edge profile Local State: {str(e)}")
            
            logger.warning(f"Configured Edge profile '{preferred_profile}' not found")
        
        # Default to the User Data directory
        logger.info(f"Using Edge User Data directory: {edge_data_dir}")
        return edge_data_dir
        
    except Exception as e:
        logger.error(f"Error finding Edge profile: {str(e)}")
        return None

def configure_edge_options(options, config=None, logger=None):
    """Configure Edge options with profile settings
    
    Args:
        options: Edge options object to configure
        config: Optional configuration dictionary
        logger: Optional logger instance
        
    Returns:
        Configured options object
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        # Add stability options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        
        # Check if profile configuration is enabled
        if config and 'EDGE_PROFILE' in config and config['EDGE_PROFILE']:
            preferred_profile = config['EDGE_PROFILE']
            user_data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Edge', 'User Data')
            
            if os.path.exists(user_data_dir):
                logger.info(f"Using Edge User Data directory: {user_data_dir}")
                options.add_argument(f"user-data-dir={user_data_dir}")
                
                # For the "Personal" profile, we need to use "Default" directory
                if preferred_profile.lower() == 'personal':
                    logger.info("Mapping 'Personal' profile to 'Default' directory")
                    options.add_argument("profile-directory=Default")
                else:
                    logger.info(f"Using profile directory: {preferred_profile}")
                    options.add_argument(f"profile-directory={preferred_profile}")
        else:
            # If no profile is specified, use a temporary profile
            logger.info("No Edge profile specified, using temporary profile")
            # Don't add user-data-dir argument
        
        return options
    except Exception as e:
        logger.error(f"Error configuring Edge options: {str(e)}")
        return options

def configure_firefox_options(options, config=None, logger=None):
    """Configure Firefox options with profile settings
    
    Args:
        options: Firefox options object to configure
        config: Optional configuration dictionary
        logger: Optional logger instance
        
    Returns:
        Configured options object
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        profile_path = get_firefox_profile_path(logger, config)
        if profile_path:
            logger.info(f"Using Firefox profile: {profile_path}")
            options.profile = profile_path
        return options
    except Exception as e:
        logger.error(f"Error configuring Firefox options: {str(e)}")
        return options

def configure_chrome_options(options, config=None, logger=None):
    """Configure Chrome options with profile settings
    
    Args:
        options: Chrome options object to configure
        config: Optional configuration dictionary
        logger: Optional logger instance
        
    Returns:
        Configured options object
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        profile_path = get_chrome_profile_path(logger, config)
        if profile_path:
            logger.info(f"Using Chrome profile: {profile_path}")
            options.add_argument(f"user-data-dir={profile_path}")
        return options
    except Exception as e:
        logger.error(f"Error configuring Chrome options: {str(e)}")
        return options

def configure_browser_options(browser_type, options, config=None, logger=None):
    """Configure browser options based on browser type
    
    Args:
        browser_type: Type of browser ('firefox', 'chrome', 'edge')
        options: Browser options object to configure
        config: Optional configuration dictionary
        logger: Optional logger instance
        
    Returns:
        Configured options object
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    browser_type = browser_type.lower()
    
    if browser_type == 'firefox':
        return configure_firefox_options(options, config, logger)
    elif browser_type == 'chrome':
        return configure_chrome_options(options, config, logger)
    elif browser_type == 'edge':
        return configure_edge_options(options, config, logger)
    else:
        logger.warning(f"No profile configuration available for browser type: {browser_type}")
        return options