import { loadAppConfig, setAppConfig } from '../../src/main/bootstrap/core/config';

setAppConfig(loadAppConfig(process.env));
