# 3. Separation runs in its own child process

Running torch inside the web server's process would be simpler, but a native crash in torch or a GPU driver reset would take the whole server down, and a separation chunk cannot be interrupted from Python once it starts. The model therefore runs in one long-lived child process started with the `spawn` method (the only method on Windows), which keeps the model loaded between jobs. Cancelling or a crash costs one model reload. The server talks to it through a multiprocessing queue and can terminate it at any time.
