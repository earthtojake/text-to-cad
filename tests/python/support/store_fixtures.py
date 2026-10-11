"""Store fixtures for tests: build a tree and lay a view of it, or seed a
document's result straight into the store without a kernel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def build_view(
    compound: Any,
    *,
    package_dir: Path,
    root_name: str,
    force: bool = False,
    provenance: Mapping[str, Any] | None = None,
    progress: Any | None = None,
) -> dict[str, Any]:
    """Build ``compound``'s tree into the store and lay a view of it at
    ``package_dir`` (the directory shape the older readers consume). Returns the
    build stats plus the tree hash under ``tree``."""
    from cadgen.store.build import build_tree_from_compound
    from cadgen.store.view import export_view

    tree_hash, _tree, stats = build_tree_from_compound(
        compound,
        root_name=root_name,
        force=force,
        progress=progress,
    )
    export_view(tree_hash, Path(package_dir))
    result = dict(stats)
    result["tree"] = tree_hash
    return result


# Proven small box inputs, generated with the named loaded producer. Keeping
# encoded inputs here lets catalog/security fixtures seed genuine geometry and
# surfaces without importing OCP in the process under test.
FIXTURE_SURFACE_PRODUCER = {'scheme': 20, 'surfFormat': 3, 'build123d': '0.11.1', 'ocp': '7.9.3.1', 'cadqueryOcp': '7.9.3.1.1'}
_GEOMETRY_FIXTURES = [{'kind': 'native', 'codec': 'bintools-v4', 'brep': '0bdb4f63f3ab902a54be4da365fe1810a2cf9fb9f688d452e8a608a8c4328f51', 'faceColors': {}, 'contentHash': '01e2a28516540a13ff82f3e0479e481eb16c24c2f60cad2cb2e518d90eecee41', 'payload': 'eJylVttu00AQXTvXuumFFih3DE8Q8QBpxCN1lSLxgFSkRLxbaRsqRXGUEKTyxHfwE/wAUvsX/EbEFzBOdmYTeyZrB6uKVzuzc87MnB3XOx2eD/zWcbt1fPLe70TDqB/1rvzPzVf+i+5Lf24Nx93w7Nz7GHXDr5fRYOy/9lqT0bfzxtnYbzQ9R7HP9AhXWR2qgeB4LUQwkZION+tyECHyc7BBoCF/HcwJG4ebdTlIzxocsjpkr0PuUtsjBP/NIRVhdkfG/puGdEOys1MJMj+SWAKZ3Aj0SAhS20WE5AFrDrSBjnkR6JEQ5IjJAJY+2A8EeRECG8KnqH/ViwaHJzCF9fp00BldhoPepE/zuT0ZXYRdUN9bm/jSCNn8pte4yi2l1QC5u5A9kETIdntSB/IC5x4AUiCJkHUoC4EsfqbJKYV5nfaXcAgKO2x6lQ+/fv/8++f7Oz5q3ChHOfBXt3jOU5l5ltHTmW3wcV1HSfoDowsvdxWj+PBz3Hum3yLHIJXNEkceSQVuQeQIxiL8FgQjcXyKW0jWxlEpniOPBKUqiRzBWIZXUTCmOT5GjkvI/HkoQEVEBmMVfkuCkZAR0HSwNE9eOb7ecZ6gzyNcPETnoiKeFNyZK+4B+iTKzX3TeIFzF5JrDJ8k1H4DXmXJ6KkMAr+Hewe2bIJUNksceRrQpU2RIxhrKoPA7+AWkrVxjB+OY4UFglJtiRzBuK0yCJw47iPHJeSqkKO7IyKDcVdlEDgCmg6SwO/qHec2+uzh4hY6G4EbGlrgu2wqGyyf6ZEbh+T1BsY9MZW4eToVzMDc1SVkTwq+vwo5zp2X2AIyXQOaoVTEbb1D1VRbuPDR2RTR0NBFrLGpbEpsYx3xYgNjzMBaRNIDP2prwnn3YBVyXB9rEekO4LQ3RcTWOSRAkhHO3IUiGhq6iHh9TEAc0EYUqGiFDVsIaIqmA6LWTUD8Bhh906XBfi8ENLXQAZFyvYAB76PHDnpS03EOmcGO8eou/jeDQqrT9+8fa241eQ==', 'surface': 'eNrNWVtvmzAUjrS/sSc/Q4VtoG1eN/V10i5PUzW5wUnoCEQGomZVfvtmUxJuvnBJJx6IUju2j7/LsQ/99uPrw4fFYvH342LxCg6UpWESgyW2QLole5qC5c9XkLAALKEFfocx/wLSJAoDYIFDEuU7Cpb+jXN6tMCarFq/L6YovjEqpqa8OWM5tUB+4D90bhwL88dG/IP/wedIcyam+X4U48A+IjHlCxFGSbGMBVY0zigrB8Pi8fi4p6fkpWysP+hthWpisHw97+I8ecLCTRg3B/MBL0HIao2waDxWjTa8/PTPW2vZYNmi9WSBKEn2Ag8OCA029EsJSgXFmkQpPVm1bqTvxm0gG71up/eRBxcnbEciHkYRsF1tcE8Y2aUCEAUC5CVMO9sSKyZlqDJ6i6CvwS+U8Qtr3MKh/ML/wK+nZehOT++tvtvX89sIT0ovHEAv7u3eCj0dubhlXq8cpzDvOap3MG8Lp5Jcu7aqitx7PT+evhs6Wm1APbsXSdrD3Nvc14Vet797x/KLZPyiseatDX43fiHUMoQN/KIB7pak53qASn5RT369XvaF1TFpoBd16K1CVdi3k/QH27fF5FHC5IXfuhQU9LoG/gxn851WHPc92LXPJh7g38a+LvT6/ew7lV8s4xePtW+Vz9+HX6TPr86A09Xkbnl+rlKRhl2sZpe3i/VUd+hVRFLeB9aUZDkT8K6SOAvjPMyO4lZOdvuIBr+2hInLeRBuacBI9JluuDrFImAdkQ2fwOdGIMEzEXQ/8M9PSR5nBXyrnB3O+ojCgkFBLAeguClYmEcY0XiTbbsJ39Ef6M3tFwvV9FIuprCCLNkzEm9odUoJTRgtxeehq6yobxS+QvPC26/hjaTVj9KhzeqnL964hnfLh3XAkRFw3AFccVDheSHuahWuvdIMRxxdSeFogMLdeeHtGRWuvGM0dz4mo0xSuNNX4d6cEEeaHA5lORwqizIT4vBKORwOzOH+vPBW53Aoy+FQecvqi/fkHA6H5vDbeSHuahWOZAqXl6V9EEdXUviQHH43L7w9o8IdmcK7deKYjDJJ4b1z+P2cEMcNxKH0xZq2MncmnZqtqq2OOBxxaireP4pybU6Q+0bItcWyM+kqPgly3BvyWVWbrkHlSKZyNCqvyO7ioyFHg1SO5gW5b4QcyyAffllpFktXgNyochGUwKEYXv6r0r+8cIHodPoH7nVxXA=='}, {'kind': 'native', 'codec': 'bintools-v4', 'brep': '92e6935c58872e596eeda474ad1f8e7dcc4d0c75f4ad9565e332ffc38683671f', 'faceColors': {}, 'contentHash': 'ed085edcb64085e841fec251451ac621ec0789496dc57f816d1eadc03b56df33', 'payload': 'eJylVstu00AUHTvPuumDFihvDCuIWEAasQRXKRILpCIlYm+laagUxVFCkMqK7+An+AGk8hf8RsUXcJ34zMT23My4WFE8mrlzzrl3ztzEO5kMxn7nqNs5On7n96JJNIqGF/6n9gv/Wf+5v1wNZ/3wdOB9iPrhl/NoPPNfep359OugdTrzW23PEdrn6i1GtgH1gAm8ZBAUUjbg93U1sBTFNRgpAibAXAcuoHgdOA3ccw0NtgH2dSheaiNC8N8acgiLOzLzX7W4G2KvTmTEfM9yMWIKM8iHZTAg5xkyG8w5BJl3UQb5sAwsYhbAcA7mDRlp1ht4ho/R6GIYjQ+PqQsn45Nxb3oejofzkezP3fn0LOyT+16bzJdnsIu7usSosJXWExQ+BXsgTpDp9uQ2FCUu3AA4IE6QsSkzQIY4dcg5h3m97udwQg47bHu19z9//fj759sbPWp8UI5w6NM0RC5TWURWEeksJvS4riM4/9GiSy93naJ481PMPUnerMYgl01Ko55JBG6J1UiLZfouMYtS42NMQaxJoxB6jXomKlWF1UiLVXqVmcW8xofQmGLW76cC1FhmWqzTd4VZlMwgVCdYWSYvHD+ZcR4h5gEG9xFcFlKnBHeWjruHmGy5g7SWNQbPRC7ANQejT5Jqv0GvKrfoCQuD38HcgSmbIJdNSqNeBp3SJquRFhvCwuC3MAWxJo3xo9NY0xJRqbZYjbS4LSwMLjXuQ2OKuc7k6O6wzLS4KywMDkJ1gtLgt5MZ5yZi9jC4gWBlcCUjMfiuNpUNTm0Myba5PZtUkIG6qylmjwPfX8cc5260mLwGsofKIm4nM7KaYgsDH8GqiEpGUsSGNpVNTm3sI7Ybxgrs/aBvtQ3tdgI/WMcc18f+nqLbqyLi6BxpQGkj9NyVIioZSRFxfRQgGrQyBRwtcGArgKpoCSC8rgDxG6D8LS8NznsFUNUiAYTkZgmAdxGxg0h56OhDqrEDr+ni3wyM1JS/f/8AfxceIg==', 'surface': 'eNrNWV1vmzAUrbTfsRc/QwXXQNu8burrpH08TdXkBidhIxAZiJpV+e+zKeEjsQ2GdKJSqtTGX+ece3wv/fbj6+OHG/7z8ebmFe0py6I0QQtsoWxDdjRDi5+vKGUhWrgW+hMl/AvK0jgKkYX2aVxsKe+BW+f4ZKEVWZ4NKOcovzEq5qa8OWcFtVCx5w86t46F+cfmE1j8Dz5HVjAxzfeDGId2MUkoX4kwStAi4E+hJU1yyqrBbvnx+bjn5/Slamx/4G2FZmK0eD0d4zR5yqJ1lHQH8wEvYcRajW7ZeGgabbd+9O9ba9Vg2aL1aKE4TXcCDw4IDdf0SwVKA8WKxBk9Wq1u0HfjcyA7vd5F7xPfXJKyLYn5NsoN280Bd4SRbSYAUSBAXqLs4lhixbTaqozectPX4Bdk/MIZt0b8wn/g19cydK+n907fHej57WxPSi8Y0IsHR2/FhRG5bo26InhPW32H4D3DqSLXPvmJhtwHPT++vtt1tNpw9ezWkrTNord7rppeb3j0juUXZPzC2OBtDX43fl1XyxDu4RcMoltiz+0NKvmFgfz6g8IXBtPrXdDbbFURvhembxy+Z0weJEzW/LaloKDX6+Gv526+14rjYQC79imIDeK3c66a3mBY+E7lF8v4xWPDt/Hz9+EX9P7qGNyufdEt9+fGijTsYjW7vF2sp8qhlzHJeB9aUZIXTMC7TJM8SoooP4i0nGx3MQ1/bQgT2XkYbWjISPyZrrk6xSJoFZM1nyDggUDC30TQ/ch/f0qLJC/hWxZsf9JHHJUMCmI5AGWmYGG+w5gm63zD3fAiG3f6svHm+OVCLb1UiylCQWb2jCRr2txSQhO9IcXnocu8LHAUcQXzwjto4Q3S6kcZod3qZyjeuIX3WRy2AYdewPEF4IqLCs8LcU+rcG1KY444XEnhYKBwb154+70KV+YY3ZOPcZRJCneGKtyfE+Kg8XCQeTgoi7I+xOFKHg6GHh7MC2+1h4PMw0GZZQ3Fe7KHg6mH380LcU+rcJApXF6WDkEcrqRwEw+/nxfefq/CHZnCL+vEMY4ySeGDPfxhTohjDeJu52SaF2vjb82zqm3qral4/yjKtTlBHvRCri2WnUmp+CTI8WDIZ1Vtej0qB5nKYZSvyHLx0ZCDkcphXpAHvZBjGeTmyUq3WLoC5L0qF5sSOJTDq39VBvULFxeOx3+XgXCi'}, {'kind': 'native', 'codec': 'bintools-v4', 'brep': '7616b493c09ff73f1a25c48badeafa1330aa0fbc821a6df7f88370fa68fa1915', 'faceColors': {}, 'contentHash': 'bca29d8e668cef75b9fa10687b2f4b3eb1535e5c4b11619bd55255a24e503011', 'payload': 'eJylVstu00AUHTvPuumDFihvDCuIWEAasQRXKRILpCIlYm+laagUxVFCkMqK7+An+AGk8hf8RsUXcJ34zMT23My4WFU8mrlzz7lnzlzXO5kMxn7nqNs5On7n96JJNIqGF/6n9gv/Wf+5v1wNZ/3wdOB9iPrhl/NoPPNfep359OugdTrzW23PEdrn6i1GtgH1gAm8ZDKoTNmA39flwEIU52CCQLnFdWADCuvAcuCea3CwDbDXobDU5gzBf3PIZVjckZn/qsXdEHt2IkPmexaLIVMYQT4cAqcHi5DdYKxBBhiQWAT5cAh8xmwCwzmYN2SoWW/gET5Go4thND48pi6cjE/Gvel5OB7OR7I/d+fTs7BP7nttMl8ewS7u6hKjwlZaD1D4FOwTcYRMtye3oShw4QbAJeIIGbsVk8gQpw455zCv1/0cTshhh22v9v7nrx9//3x7o88as3KEQ39NQ+SylEVkFZHOYkKf13UE5z9adOnlrmMUb36KuSfJm+UY5KpJcdQjicAtsRxpsUy/JWZRcnyMKZA1cRRCz1GPRFJVWI60WKVXmVnMc3wIjilk/X4SoMYi02KdfivMokQGoDrByrJ44fjJjPMIMQ8wuI/gspA8ZXJn6bh7iMnIrfum6Q2uu5C6g9EXSdpv0KvKLXrCwuB3MHdgqibIVZPiqKdBp7TJcqTFhrAw+C1MgayJY/zoONa0QCTVFsuRFreFhcElx31wTCHXmRrdHRaZFneFhcEBqE5QGvx2MuPcRMweBjcQrAyuaCQG39WWsqHlQzrFKTm/uXtsKSsiogJ1V1PIHpd8fx1yXDvX2fLXQPZQKeJ2MiPVFFsY+AhWIioaiYgNbSmbHNvYR5zZ3JiBUUTpB32rbTD73YN1yLE+RhHlHUC3VyLi6BxpQGkj9NwVERWNRERcH5UQDVqZAo4WOLCVhEq0JCG8rhLiG6D8LS8NznslodIiSQjKzRIS3kXEDiLloaMPqcaOfE0X/83ASE35/fsHBFke6g==', 'surface': 'eNrNWV1vmzAUrbTfsRc/QwW+hCZ53dTXSft4mqrJDU7CRiAyEDWr8t9nUxI+YhsM6UQlotTGX+ece7iXfPvx9fHDHf/7eHf3ig6UpWESoyVYKN2SPU3R8ucrSliAlq6F/oQx/4LSJAoDZKFDEuU7ynvm987pyUJrsmoNKOYovjEq5qa8OWM5tVB+4Dc6944F/LIx/+D/8DnSnIlpvh/FOLSPSEz5SoRRgpY+vwutaJxRVg52i2vGxz0/Jy9lY/3CbytUE6Pl6/kY58kTFm7CuDmYD3gJQlZrdIvGY9Vou5db/761lg2WLVpPFoqSZC/w4IDQYEO/lKBUUKxJlNKTVevG+m5oA9no9a56n/jm4oTtSMS3UWzYrg64J4zsUgGIAgHyEqZXxxIrJuVWZfQWm74FvyDjF2rcgim/8B/4nWkZmuvpfdB3+3p+G9uT0gsG9ELv6HXaHEjJXTTI5aSWqCuCVzrxbYK3hVNJrn32Ew25Cz0/M32362i14erZvUjSNove5rku9Hr9o3cov1jGLx4avLXB78av62oZgg5+sUF0S+y5vkElv7gnvzOj8MWG3izorbaqCN8r0zcO3xaTRwmTF37rUlDQ63Xw1/FsnmvFsejBrn0OYoP4bZzrQq9vFr5D+QUZvzA0fCsjeR9+sd5fHYOna1d0y/25siINu6Bml7eL9VQ59CoiKe9Da0qynAl4V0mchXEeZkeRlpPdPqLBry1hIjsPwi0NGIk+0w1Xp1gErSOy4RP4PBBI8JsIuh/556ckj7MCvlXODmd9RGHBoCCWA1BkChbwHUY03mRb7oZX2bjTlY1Xxy8WqumlXEwRCjKzZyTe0ErmQhOdIcXnoausKHAUcYWnhbdfwxtLqx9lhDarn754Qw3vVhzWAcedgMMV4IoHFUwLcU+rcG1KY444vpHCsYHCvWnhPetUuDLHaJ58iKOMUrjTV+GzKSGONR4OMg8HZVHWhTjcyMPB0MP9aeGt9nCQeTgos6y+eI/2cDD18IdpIe5pFY5lCpeXpX0QxzdSuImHz6eF96xT4Y5M4dd14hBHGaXw3h6+mBLi0EAcpC/WtJW5M+qp2araxibiivePolybEuR+J+TaYtkZlYqPghx6Qz6patPrUDmWqRwP8hVZLj4YcmykcjwtyP1OyEEGuXmy0iyWbgB5p8rFpgQOxfDyp0r/8sLFxafTPxKCcQc='}, {'kind': 'native', 'codec': 'bintools-v4', 'brep': '26411db2df8fa77051b37dfbed5925185810d476a1d9a555a0ca36ad058fdf45', 'faceColors': {}, 'contentHash': 'cbccb6aabd344d5ca5314286fa349e93ba29d7162354f7b55790f62395ac9f9d', 'payload': 'eJylVs1u00AQXju/ddPWtED5x3CCiAOkEUdwlSJxQCpSIu5W2oZKURwlBKmceA5eghdAKm/Ba1Q8AePEM5vYM9l1sap4tTM73zcz347rHY9PR0HnsNs5PHoX9OJxPIwHF8Gn9ovgWf95sLBG0350cup9iPvRl/N4NA1eep3Z5Otp62QatNqeo9jn6i2ubB3qoeB4KUTQkbIOv6/LQYQozsEE4YeCg7EOvuRQuA4iB+m5BgdbB/s6FC61OUL43xxyEeZ3ZBq8akk3xJ6dypD5nsUSyBRGoEdCkNouImQPGHOgAwYkEYEeCUGOmA1g6IP5QIaa9QEZ4WM8vBjEo4MjmMLp+njUm5xHo8FsSPO5O5ucRX1Q32uT+PIIdn5Xl7gqLKX1AIW7YB9IImS6PbkDRYELDwApkETIOJSFQAY/3eScwrxe93M0BoUdtL3a+5+/fvz98+0NHzVplKMc+GsaPBepzD2r6OnMN/i4rqMk/YHRhZe7jlFy+CnuPUnfIscwl80KRx5JhW5J5AjGMvyWBCNxfIxbSNbEUSmeI48EpaqIHMFYhVdZMOY5PkSOK8j8eShATUQGYx1+K4KRkBFQd7CySF45QbrjPEKfB7i4j85lRTwpuLNQ3D30yZSb+6bxAucuJNcYPkmo/Qa8qpLRUxYCv4N7+6Zswlw2Kxx5GtClTZEjGBvKQuC3cAvJmjgmD8exxgJBqbZEjmDcVhYCJ457yHEFuS7k6O6IyGD0lYXAEVB3kAR+O91xbqLPLi5uoLMWuKaRCtxnU9lg+fihm4Tk9QbGXTEVX6eCGei7uoLsScH31iEnufMSW0Kma0AzlIq4ne5QNdUWLgJ01kXUNNIiNthUNiW2iY54sYExYWAsIumBH7UN4by7vw45qY+xiHQHcNrrImLrHBIgyQhn7lIRNY20iHh9dEAc0FoUqGiFDVsKqIuWBkSt64D4DdD6pkuD/V4KqGuRBkTKzRIGvIseO+hJTcc5pAc7xmu6+N8MCqlJ379/iYwfsg==', 'surface': 'eNrNWcuOmzAUjdrv6MZrGIFtmEy2rWZbqY9VNao8wUloCUQGoklH+ffalPAIfvDIVCyIMnb8Oufc43uZr9+/PL5fLBbvPiwWr+BIWRomMVghC6Q7cqApWP14BQkLwMq1wO8w5l9AmkRhACxwTKJ8T8EK4jvn/GSBDVlfDSjmKL4xKuamvDljObVAfuQ/dO4cC/HHhvyD/8HnSHMmpvl2EuPAISIx5SsRRglY+fxXYE3jjLJysFs8Hh/3/Jy8lI3NB/5boZ4YrF4vx7hMnrBwG8btwXzASxCyRqNbNJ7qRtutfvrnX2vZYNmi9WyBKEkOAg8OCA229HMJSg3FhkQpPVuNbqjvRtdAtnpxp/eJby5O2J5EfBvFhu36gAfCyD4VgCgQIC9h2jmWWDEptyqjt9j0LfjFMn5xg1s8lF/8H/j1tAwt9fTe67t9Pb+t7UnpxQPoRb2jt+TCQK4LW+zCCnZF9F72+gbRewVUya59MRQNuw96gjx9t+toxeHq6a00aQ8L3/a5Kn5x//AdTTCUEQzHhm9j8JsR7LpaipCBYDggviUG3dygkmDYk2CvVwDj+qI08Lvs0FtvVRG/HdsfHL9XTJ4kTFb8NqWgoBcb+DPczkutOB56sGtfonhAALfOVdHr94vfqfwiGb9obPjWhv42/EK9wToD7ldTdMsNurYiDbtIzS5vF+upsuh1RFLeBzaUZDkT8K6TOAvjPMxOIjEn+0NEg587wkR+HoQ7GjASfaJbrk6xCNhEZMsn8HkgkOAXEXQ/8s+PSR5nBXzrnB0v+ojCgkFBLAegyBUsxHcY0Xib7bgbdvJxx5SP18cvFmropVxMEQoys2ck3tL6mhKaMIYUn4eus6LEUcQVnBfefgNvKK1/lBHarn/64o0aeF/FYRNwaAQcdQBXXFRoXohjrcK1Kc1wxOGNFA4HKBzPC2/PqHBljtE++RhHmaRwp6/CvTkhDjUejmUejpVVmQlxfCMPxwM93J8X3moPxzIPx8osqy/ekz0cD/Xw+3khjrUKhzKFy8vSPojDGyl8iIcv54W3Z1S4I1N4t04c4yiTFN7bwx/mhDhqIY6lb9a0lbkz6da8qtqaiOMRt6biDaQo1+YEuW+EXFssO5NS8UmQo96Qz6raxAaVQ5nK4ShfkeXioyGHg1QO5wW5b4QcySAfnqy0i6UbQG5UudiUwKEYXv6z0q9euLjwfP4Lm4Zxaw=='}]

def seed_result(
    document: Path | str,
    descriptor: Mapping[str, Any] | None = None,
    *,
    model: Path | str | None = None,
    surf: bytes = b"SURF\x00",
    components: tuple[str, ...] = ("c0",),
    kind: str = "assembly-package",
    entry_kind: str = "part",
    sidecar: Mapping[str, Any] | None = None,
) -> str:
    """Seed geometry and an optional surface derivation without native imports.

    Caller aliases are remapped to genuine geometry CIDs. The historical default
    SURF sentinel selects valid fixture bytes; other payloads deliberately test
    corrupt disposable surfaces. Explicit malformed structure/geometry overrides
    stay malformed so completeness checks can reject them.
    """
    import base64
    import copy
    import zlib
    from cadgen._internal.component_package import canonical_json_bytes
    from cadgen.store.index import write_entry
    from cadgen.store.objects import is_object_hash, put_object
    from cadgen.store.records import note_document_tree, note_output, write_record
    from cadgen.store.surfaces import _expected
    from cadgen.store.trees import TREE_KIND, TREE_SCHEMA, tree_kind

    document = Path(document)
    descriptor = copy.deepcopy(dict(descriptor or {}))
    raw_components = descriptor.get("components")
    if not isinstance(raw_components, dict):
        raw_components = {cid: {} for cid in components}
    if len(raw_components) > len(_GEOMETRY_FIXTURES):
        raise ValueError("seed_result supports at most four independent fixture components")
    tree_components, aliases, component_colors = {}, {}, {}
    for index, (alias, raw_entry) in enumerate(raw_components.items()):
        fixture = _GEOMETRY_FIXTURES[index]
        payload = zlib.decompress(base64.b64decode(fixture["payload"]))
        entry = {name: copy.deepcopy(fixture[name]) for name in ("kind", "codec", "brep", "faceColors", "contentHash")}
        put_object(payload)
        raw_entry = dict(raw_entry or {})
        if raw_entry.get("color") is not None:
            entry["color"] = raw_entry["color"]
            component_colors[alias] = raw_entry["color"]
        if "brepObject" in raw_entry:
            entry["brep"] = raw_entry["brepObject"]
        cid = entry["contentHash"][:16]
        aliases[alias] = cid
        tree_components[cid] = entry
        surface = zlib.decompress(base64.b64decode(fixture["surface"])) if surf == b"SURF\x00" else surf
        surface_hash = put_object(surface)
        if is_object_hash(raw_entry.get("surfObject")):
            surface_hash = raw_entry["surfObject"]
        expected = _expected(entry, FIXTURE_SURFACE_PRODUCER)
        write_entry("surface", expected["surfaceInput"], {**expected, "object": surface_hash})
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    occurrences = descriptor.get("occurrences")
    if not isinstance(occurrences, list):
        occurrences = [{"id": f"o1.{i}" if len(aliases) > 1 else "o1", "name": alias,
                        "component": cid, "transform": identity}
                       for i, (alias, cid) in enumerate(aliases.items(), 1)]
    else:
        for occurrence in occurrences:
            occurrence["component"] = aliases.get(occurrence.get("component"), occurrence.get("component"))
    children = [{"id": occurrence["id"], "name": occurrence.get("name", occurrence["id"]),
                 "nodeType": "part", "children": []} for occurrence in occurrences]
    assembly = descriptor.get("assembly")
    if not isinstance(assembly, dict):
        root = children[0] if len(children) == 1 and children[0]["id"] == "o1" else {
            "id": "o1", "name": descriptor.get("label") or "model", "nodeType": "assembly", "children": children}
        assembly = {"root": root}
    tree = {"kind": TREE_KIND, "schemaVersion": TREE_SCHEMA,
            "label": descriptor.get("label") or "model", "units": "mm",
            "components": tree_components, "occurrences": occurrences, "links": [],
            "assembly": assembly, "stats": {"occurrenceCount": len(occurrences), "linkCount": 0}}
    tree["entryKind"] = tree_kind(tree)
    if descriptor.get("kind") not in (None, kind):
        tree["kind"] = descriptor["kind"]
    for key in ("bbox", "capabilities", "edgeRendering", "color"):
        if key in descriptor:
            tree[key] = descriptor[key]
    # Deliberately malformed fixture knobs must remain malformed; production
    # publication goes through put_tree and native preparation instead.
    tree_hash = put_object(canonical_json_bytes(tree))
    try:
        sha = hashlib.sha256(document.read_bytes()).hexdigest()
    except OSError:
        sha = ""
    owner = Path(model) if model is not None else document
    record = {"entryKind": tree["entryKind"], "sourceKind": "python" if model is not None else "step",
              "tree": tree_hash, "closure": {"hash": sha, "files": [], "static": True}, "children": [],
              "outputs": {str(document.resolve()): {"sha256": sha}}, "stepHash": sha}
    if sidecar:
        record.update(sidecar)
    write_record(owner, record)
    if sha:
        note_document_tree(sha, tree_hash, kind="step", surface_producer=FIXTURE_SURFACE_PRODUCER)
    if model is not None:
        note_output(document, owner)
    return tree_hash


def read_view_descriptor(view_dir: Path | str) -> dict[str, Any]:
    return json.loads((Path(view_dir) / "assembly.json").read_text(encoding="utf-8"))
