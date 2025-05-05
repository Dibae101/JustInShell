import os
import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings

logger = logging.getLogger(__name__)

def get_encryption_key():
    """
    Get or generate the encryption key for sensitive data.
    Uses PBKDF2 to derive a key from the Django SECRET_KEY.
    """
    # Use Django's SECRET_KEY as the password for deriving the encryption key
    password = settings.SECRET_KEY.encode()
    
    # Use a fixed salt stored in environment or settings
    salt = getattr(settings, 'ENCRYPTION_SALT', None)
    if not salt:
        # Fallback to a derived salt if not configured
        salt = settings.SECRET_KEY[:16].encode()
    else:
        salt = salt.encode()
    
    # Use PBKDF2 to derive a key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    
    # Generate the key
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return key

def encrypt_value(value):
    """
    Encrypt a value using Fernet symmetric encryption
    """
    if not value:
        return value
    
    try:
        # Convert the value to bytes if it's a string
        if isinstance(value, str):
            value_bytes = value.encode('utf-8')
        else:
            value_bytes = value
        
        # Create a Fernet cipher with our key
        key = get_encryption_key()
        cipher = Fernet(key)
        
        # Encrypt the value
        encrypted_value = cipher.encrypt(value_bytes)
        
        # Return as a string for storing in the database
        return encrypted_value.decode('utf-8')
    except Exception as e:
        logger.error(f"Error encrypting value: {str(e)}")
        # Return the original value if encryption fails
        # This is a fallback to prevent data loss, but should be handled better
        return value

def decrypt_value(encrypted_value):
    """
    Decrypt a value that was encrypted with encrypt_value
    """
    if not encrypted_value:
        return encrypted_value
    
    try:
        # Convert the encrypted value to bytes if it's a string
        if isinstance(encrypted_value, str):
            encrypted_bytes = encrypted_value.encode('utf-8')
        else:
            encrypted_bytes = encrypted_value
        
        # Create a Fernet cipher with our key
        key = get_encryption_key()
        cipher = Fernet(key)
        
        # Decrypt the value
        decrypted_value = cipher.decrypt(encrypted_bytes)
        
        # Return as a string
        return decrypted_value.decode('utf-8')
    except Exception as e:
        logger.error(f"Error decrypting value: {str(e)}")
        # Return None on decryption failure
        return None

def generate_random_key(length=32):
    """
    Generate a random key for various security purposes.
    """
    return base64.urlsafe_b64encode(os.urandom(length)).decode('utf-8')

def hash_password(password):
    """
    Create a secure hash of a password. 
    Note: Django's auth system handles password hashing automatically,
    but this can be useful for other password storage needs.
    """
    import hashlib
    import binascii
    import os
    
    # Generate a random salt
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode('ascii')
    
    # Hash the password with the salt
    pwdhash = hashlib.pbkdf2_hmac('sha512', 
                                  password.encode('utf-8'),
                                  salt, 
                                  100000)
    pwdhash = binascii.hexlify(pwdhash)
    
    # Return the salt and hash
    return (salt + pwdhash).decode('ascii')

def verify_password(stored_password, provided_password):
    """
    Verify a password against its hash.
    """
    import hashlib
    import binascii
    
    # Extract the salt from the stored password
    salt = stored_password[:64]
    
    # Extract the stored hash
    stored_hash = stored_password[64:]
    
    # Hash the provided password with the same salt
    pwdhash = hashlib.pbkdf2_hmac('sha512',
                                  provided_password.encode('utf-8'),
                                  salt.encode('ascii'),
                                  100000)
    pwdhash = binascii.hexlify(pwdhash).decode('ascii')
    
    # Compare the hashes
    return pwdhash == stored_hash

def generate_ssh_key_pair(key_type='rsa', key_size=2048, passphrase=None):
    """
    Generate a new SSH key pair
    
    Args:
        key_type (str): Type of key ('rsa', 'dsa', 'ecdsa', 'ed25519')
        key_size (int): Size of key in bits (for RSA)
        passphrase (str): Optional passphrase to protect the key
    
    Returns:
        tuple: (private_key, public_key) as strings
    """
    try:
        import paramiko
        
        if key_type == 'rsa':
            key = paramiko.RSAKey.generate(key_size)
        elif key_type == 'dsa':
            key = paramiko.DSSKey.generate(key_size)
        elif key_type == 'ecdsa':
            key = paramiko.ECDSAKey.generate()
        elif key_type == 'ed25519':
            key = paramiko.Ed25519Key.generate()
        else:
            raise ValueError(f"Unsupported key type: {key_type}")
        
        # Get public key as string
        public_key = f"{key.get_name()} {key.get_base64()}"
        
        # Write private key to string
        private_key_file = paramiko.PKey()
        private_key_data = io.StringIO()
        key.write_private_key(private_key_data, password=passphrase)
        private_key = private_key_data.getvalue()
        
        return private_key, public_key
    
    except Exception as e:
        logger.error(f"Error generating SSH key pair: {str(e)}")
        raise


def validate_ssh_credentials(hostname, port, username, auth_type, password=None, ssh_key=None, ssh_key_passphrase=None):
    """
    Validate SSH credentials by attempting to connect
    
    Args:
        hostname (str): Server hostname or IP
        port (int): SSH port
        username (str): SSH username
        auth_type (str): Authentication type ('password', 'key', 'key_with_password')
        password (str): Password (for password auth)
        ssh_key (str): Private key (for key-based auth)
        ssh_key_passphrase (str): Passphrase for private key
    
    Returns:
        bool: True if connection successful, False otherwise
    """
    import paramiko
    import io
    import socket
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        connect_kwargs = {
            'hostname': hostname,
            'port': port,
            'username': username,
            'timeout': 5,  # Short timeout for validation
        }
        
        # Add authentication info based on auth type
        if auth_type == 'password':
            connect_kwargs['password'] = password
        
        elif auth_type == 'key':
            # Create in-memory file-like object for the key
            key_file = io.StringIO(ssh_key)
            # Load the key
            private_key = paramiko.RSAKey.from_private_key(key_file)
            connect_kwargs['pkey'] = private_key
        
        elif auth_type == 'key_with_password':
            # Create in-memory file-like object for the key
            key_file = io.StringIO(ssh_key)
            # Load the key with passphrase
            private_key = paramiko.RSAKey.from_private_key(
                key_file, password=ssh_key_passphrase
            )
            connect_kwargs['pkey'] = private_key
            
        else:
            raise ValueError(f"Unsupported auth type: {auth_type}")
        
        # Attempt to connect
        client.connect(**connect_kwargs)
        
        # Close the connection
        client.close()
        
        return True
    
    except (paramiko.AuthenticationException, paramiko.SSHException, socket.error) as e:
        logger.warning(f"SSH validation failed: {str(e)}")
        return False
    
    except Exception as e:
        logger.error(f"Unexpected error in SSH validation: {str(e)}")
        return False
    
    finally:
        try:
            client.close()
        except:
            pass