"""The engine's CAD Viewer HTTP application and its short-lived launcher.

``cadgen viewer [FILE ...]`` ensures the installation's engine and opens its one
page: the home, or each file's page. The built React client ships in
``cadgen/_runtime/viewer``. The page addresses every document by path, ``/<id>``; a
request names a file by its absolute path.

No HTTP request thread imports OCP or build123d. Document reads, topology,
poses and meshes run in the engine's worker processes. The application holds
plain data and dispatches document routes in process, without a relay.
"""
