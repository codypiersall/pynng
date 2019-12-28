from pynng import Pair0, TLSConfig

SERVER_CERT = """
-----BEGIN CERTIFICATE-----
MIID1jCCAr6gAwIBAgIUMq6zvsPyDm2s4dRJD3SLYmRW1BYwDQYJKoZIhvcNAQEL
BQAwgY0xCzAJBgNVBAYTAk5MMRAwDgYDVQQIDAdMaW1idXJnMSswKQYDVQQHDCJL
YXJ2ZWVsd2VnIDE5QiwgNjIyMiBOSiBNYWFzdHJpY2h0MRMwEQYDVQQKDApWZWN0
aW9uZWVyMRQwEgYDVQQLDAtEZXZlbG9wbWVudDEUMBIGA1UEAwwLTW90b3Jjb3J0
ZXgwIBcNMTkxMjA2MTEwODIwWhgPMjExOTExMTIxMTA4MjBaMIGNMQswCQYDVQQG
EwJOTDEQMA4GA1UECAwHTGltYnVyZzErMCkGA1UEBwwiS2FydmVlbHdlZyAxOUIs
IDYyMjIgTkogTWFhc3RyaWNodDETMBEGA1UECgwKVmVjdGlvbmVlcjEUMBIGA1UE
CwwLRGV2ZWxvcG1lbnQxFDASBgNVBAMMC01vdG9yY29ydGV4MIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAz7ai7pvSp+tAadRgeQrO0rZ8kmCDtHbN5xLV
jZBHtr7lKlKZkyJfeV1ERgO2jPqnQ9uMIR52HHxQsKEzyveFoAmjrB0cQfJz35c4
i8eLwDRnEv4lK9JVLhtoUIYrUjN8LzeeBEztBCCh0X8p7vcLX4+9Y679edzWdNGM
HUpIVTrbg7qvpITe/VbBMYnkCaQU3HgMnpEpMA1EcYAovMHmss5ZLR4cA/FG2D7E
3FiFQCYic17/OMzr1r/3ybD0mNwwkJV0R2HnexGXmQ00W/QogAjAD4UjBXFjrlpp
78MR1rOyvKbSssSJEtzLw+eJUHce3xYRLbnk1kxkB9gi753frQIDAQABoyowKDAm
BgNVHREEHzAdgglsb2NhbGhvc3SHBH8AAAGHBMCoso+HBMCoAmQwDQYJKoZIhvcN
AQELBQADggEBAJS21jEXoQrA2U2JajV69BsetOpgE4Yj0cWbK1ujX4j5leTW5m+h
qGOxj3vUCK4OakSqDtaxCI0Kqf1eghFge0nmUJdtz3/slqn0enIBcVRdZTDjP5+S
+rFJBhCPRu+LnIsdPauO1zWHNWK1e+rrn1JXINpNvAkrCHkJE/gxNFKOSwD3bFB6
tiGfIzxrWPAe+9yWJKG8swFzEWqIbw+1TgxBiqHGU+H/MZLUxswzQXDjOzClbKwd
4qDP9+0NM2Yorq1QHaXcJO+Xkja27PD7RMXxSqpOqI3jygw2SIgkG2dZ7tqIyQMi
QlwvysgNBjtSmQ1wPjSbEYGqtvoSK4bWTsA=
-----END CERTIFICATE-----"""

SERVER_KEY = """
-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDPtqLum9Kn60Bp
1GB5Cs7StnySYIO0ds3nEtWNkEe2vuUqUpmTIl95XURGA7aM+qdD24whHnYcfFCw
oTPK94WgCaOsHRxB8nPflziLx4vANGcS/iUr0lUuG2hQhitSM3wvN54ETO0EIKHR
fynu9wtfj71jrv153NZ00YwdSkhVOtuDuq+khN79VsExieQJpBTceAyekSkwDURx
gCi8weayzlktHhwD8UbYPsTcWIVAJiJzXv84zOvWv/fJsPSY3DCQlXRHYed7EZeZ
DTRb9CiACMAPhSMFcWOuWmnvwxHWs7K8ptKyxIkS3MvD54lQdx7fFhEtueTWTGQH
2CLvnd+tAgMBAAECggEAI4UA0brVyB9DkZVetfQyL/hCzykv/IFAbp5a5G1ixg5Y
0+byGiYLm45maW6jHfKS/diiWtuBqRddGQdH+xJeyGI9meYUefaC+B487jI+ZKzR
X38UTi0Wod7P9M0sxU7GkrB5FhUthsIpydBsFFAsorfK1CwNbnRkO+/FfRDB08kA
sGu1qGc8Do4Bt8w8fevqHNaexbAX7RaokK3gWf4+kYn7drwl2Lp/8qSq+WNN4dYE
x0fRiGQ/eMP+hPHWY0PIq9InjX0bl0sVeKBhVV4OLp8Vy7neY/11aEAj3lvioMog
kimmmd7llQDqo3bUt/rPyi1z1BIuy1t1nVIug8SvwQKBgQD6/gotZJ1v7Scz2VtP
FQxfYupgoMdBlUiaBcIjPisAjTNDAG8i54TZa4/ELC1f5yulu0vbsoLpalW3f2I0
4Eog1NiYteAwZxH85fVd5WTPBe+WRXyeAJl0ZRnmx/0oF7ToDdUpDFlIgBPzCfiK
oqH5kNwef4UBXBzNCqwETpDDcQKBgQDT24v1Wi0AsPmo2gtxYq+aC9KHdWWiIp/O
I6+PrIkigLDJiw5ltXZ8VnGEt/l03EI4+60O6l5jb9SxP+fs8pCOJ6Dpjm5ATxPZ
NEu2/c2+YZrJdxNeB4UBi1Lrw6iPbsywaC8MuwMIYdf/5KOWG9TsLQHeXHl9IQBl
p0PVlCnJ/QKBgBGKV2O8uFPuGuNAuWTZb7fqzb5a/hHTQPOim2KjIZY0R/TSvvGN
hHc9URrAi5s8KIy4fiCoZQWy7LKaMF7JneSVe12QuE4ppdQqre8V7Oma3Jd/26mf
GRpNRnYeW87FeVsOPGtV9ZdffAVsGPZ3TyKFwRxQhRcHPOwHZuYWJ3/BAoGBAJSG
ERuj6XLXn19x5Z3K+qK7cQ/IDMVbEr+YowbNhaJrqATTePdy/Sr0C0dpFviHReHf
Bxcy1ZNOnkTZMYYbE56lR5kVYlOxXI/kqsQSMMAsezCMS0abbPKFM0/X7n8HxXZS
w9Ff9iNVPPHH36tnvaEJeIrkN8OydC3P0q2T3qwdAoGBANfSSQYCe7wBiS0YoNBZ
NLtTIoIHJEcqpILFLN37tnFEeOT98WBGg9LRRmyzsc2x5UmbZYiB0CRf6QsJHXdX
xK0rEGEfoh9GVozhNptOtDV8agUoX9Am/bU/kGa21j9GHvjq3j0C8RMXDba/RQXS
nFcJUXxIIJLAKbqnMRIp46OP
-----END PRIVATE KEY-----
"""

# we use a self-signed certificate
CA_CERT = SERVER_CERT

URL = "tls+tcp://localhost:55555"
BYTES = b"1234567890"


def test_config_string():
    with Pair0(recv_timeout=1000, send_timeout=1000) as server, \
            Pair0(recv_timeout=1000, send_timeout=1000) as client:
        c_server = TLSConfig(TLSConfig.MODE_SERVER,
                             own_key_string=SERVER_KEY,
                             own_cert_string=SERVER_CERT)
        server.tls_config = c_server
        c_client = TLSConfig(TLSConfig.MODE_CLIENT,
                             ca_string=CA_CERT)
        client.tls_config = c_client

        server.listen(URL)
        client.dial(URL)
        client.send(BYTES)
        assert server.recv() == BYTES
        server.send(BYTES)
        assert client.recv() == BYTES


def test_config_file(tmp_path):
    ca_crt_file = tmp_path / "ca.crt"
    ca_crt_file.write_text(CA_CERT)

    key_pair_file = tmp_path / "key_pair_file.pem"
    key_pair_file.write_text(SERVER_CERT + SERVER_KEY)

    with Pair0(recv_timeout=1000, send_timeout=1000) as server, \
            Pair0(recv_timeout=1000, send_timeout=1000) as client:
        c_server = TLSConfig(TLSConfig.MODE_SERVER,
                             cert_key_file=str(key_pair_file))
        server.tls_config = c_server
        c_client = TLSConfig(TLSConfig.MODE_CLIENT,
                             ca_files=[str(ca_crt_file)])
        client.tls_config = c_client

        server.listen(URL)
        client.dial(URL)
        client.send(BYTES)
        assert server.recv() == BYTES
        server.send(BYTES)
        assert client.recv() == BYTES
