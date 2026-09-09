"""One diagnostic request; does not retry a rate-limited response."""
import urllib.request,urllib.error,pathlib
url='https://handasi.complot.co.il/magicscripts/mgrqispi.dll?appname=cixpa&prgname=GetBakashaFile&siteid=121&b=20160770&arguments=siteid,b'
request=urllib.request.Request(url,headers={'User-Agent':'ShakedPOC/0.1 public-data research','Referer':'https://handasa.herzliya.muni.il/tikbinyan/','Accept':'text/html','X-Requested-With':'XMLHttpRequest'})
try:
    response=urllib.request.urlopen(request,timeout=25)
except urllib.error.HTTPError as error:response=error
print('Status',response.status)
print(response.headers)
body=response.read();pathlib.Path('data/verification/permit-access.txt').write_bytes(body)
print(body[:2500].decode('utf8',errors='replace'))
